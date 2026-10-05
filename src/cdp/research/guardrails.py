"""Guardrails determinísticos da camada de IA (R7 — verificador).

Tudo aqui é código puro e testado; nenhuma decisão depende de um LLM:

- :func:`sanitize_untrusted` limpa conteúdo NÃO confiável (notícias, textos externos):
  remove comentários HTML, tags, caracteres de largura zero e de controle bidirecional,
  blobs Base64 longos e URLs de links Markdown; normaliza espaços, trunca e devolve flags.
  Nunca levanta exceção.
- :func:`detect_injection` procura padrões de injeção de instruções (pt/es/en), inclusive
  ocultos em comentários HTML, codificados em Base64/percent-encoding, espaçados ou com
  homóglifos. Item suspeito é removido do contexto dos analistas e registrado.
- :func:`find_free_numbers` acha números escritos fora de placeholders ``{{fact:<id>}}``
  (datas ISO, anos e rótulos de trimestre como ``3T26``/``Q3 2026`` são permitidos).
- ``verify_*``: verificação de cada saída de agente (números livres, fatos inexistentes,
  evidências inválidas ou posteriores ao ``as_of``, incoerências de stance/abstenção e padrões
  de injeção na própria saída). Qualquer problema ⇒ o chamador converte a saída em abstenção
  (ou ``caution`` no risco de short) e registra os problemas com o prefixo ``VERIFICADOR:``.
- :func:`ai_kill_switch`: degradação automática para "somente quant".
"""

from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
import urllib.parse
from collections.abc import Iterable, Mapping
from datetime import date, datetime

from pydantic import BaseModel

from ..contracts import FactBook
from .schemas import (
    AnalystOutput,
    DebateOutput,
    JudgeOutput,
    MacroOutput,
    NewsOutput,
    ShortRiskOutput,
    output_texts,
)

VERIFIER_PREFIX = "VERIFICADOR:"
INJECTION_FLAG_PREFIX = "injecao:"
UNKNOWN_FACT_TEXT = "[fato inexistente]"
DEFAULT_MAX_LEN = 500
BASE64_MIN_REMOVE = 81
"""Blobs Base64 com mais de 80 caracteres são removidos do texto limpo."""
BASE64_MIN_SCAN = 16
"""Tokens com cara de Base64 a partir deste tamanho são decodificados e inspecionados."""
KILL_SWITCH_ISSUE_RATE = 0.05
"""Fração de notas com falha em gate determinístico que desliga a IA (docs/research/07 §6.6)."""

DEFAULT_ALLOWED_TERMS: tuple[str, ...] = ("COVID-19", "Covid-19", "S&P 500", "Nasdaq-100",
                                          "IPCA-15")

# ==========================================================
# Normalização e padrões de injeção
# ==========================================================

_CONFUSABLES = str.maketrans({
    # Cirílico/grego que imitam letras latinas (ataques por homóglifos).
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
    "ј": "j", "ѕ": "s", "к": "k", "м": "m", "т": "t", "в": "b", "н": "h", "г": "r",
    "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o", "Р": "p",
    "С": "c", "Т": "t", "Х": "x", "І": "i", "Ј": "j", "Ѕ": "s",
    "α": "a", "ο": "o", "ρ": "p", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "τ": "t",
    "υ": "u", "χ": "x", "Α": "a", "Β": "b", "Ε": "e", "Ι": "i", "Κ": "k", "Μ": "m",
    "Ν": "n", "Ο": "o", "Ρ": "p", "Τ": "t", "Χ": "x",
})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a",
                       "$": "s"})

_P = re.compile


def _rx(pattern: str) -> re.Pattern[str]:
    return _P(pattern)


INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # "ignore as regras anteriores", "desconsidere as instruções" (pt)
    ("ignorar_regras_pt", _rx(
        r"\b(ignore|ignorem|ignora|desconsidere|desconsiderem|esqueca|esquecam|descarte)\b"
        r"[^.;\n]{0,40}\b(regras|instrucoes|instrucao|orientacoes|diretrizes|comandos|"
        r"restricoes|limites)\b")),
    # "ignora las instrucciones", "olvida las reglas" (es)
    ("ignorar_regras_es", _rx(
        r"\b(ignora|ignore|ignoren|olvida|olvide|olviden|omite|omita|descarta)\b"
        r"[^.;\n]{0,40}\b(reglas|instrucciones|indicaciones|restricciones|limites)\b")),
    # "ignore previous instructions", "disregard the rules" (en)
    ("ignorar_regras_en", _rx(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.;\n]{0,60}"
        r"\b(instructions?|rules?|prompts?|guidelines?|constraints?|guardrails?)\b")),
    ("ignorar_anteriores_en", _rx(r"\bignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\b")),
    # "aprove a carteira", "approve the portfolio", "apruebe la cartera"
    ("aprovar_carteira", _rx(
        r"\b(aprove|aprovem|approve|apruebe|aprueben|autorize|autorizem|authorize|sign off)\b"
        r"[^.;\n]{0,30}\b(carteira|portfolio|portafolio|cartera|book|alocacao|allocation|"
        r"trades?|ordem|ordens|orders?|operacao|operaciones|proposta|proposal|propuesta)\b")),
    ("aprovar_tudo_en", _rx(r"\bapprove\s+(this|all|everything|it|immediately|now)\b")),
    ("prompt_de_sistema", _rx(
        r"\b(system\s*prompt|prompt\s+do\s+sistema|prompt\s+de\s+sistema|prompt\s+del\s+sistema|"
        r"instrucoes\s+do\s+sistema|system\s+message|mensagem\s+do\s+sistema|"
        r"mensaje\s+del\s+sistema|developer\s+message)\b")),
    ("marcador_de_papel", _rx(
        r"(^|[\s\[<(|>\"'])(system|assistant|assistente|asistente|developer)\s*:")),
    ("tokens_de_chat", _rx(
        r"<\|?\s*(im_start|im_end|system|endoftext|assistant)\s*\|?>|\[/?inst\]|"
        r"#{2,}\s*(instruction|instrucao|instruccion|system|sistema)")),
    ("troca_de_persona", _rx(
        r"\b(voce\s+agora\s+e|voce\s+e\s+agora|a\s+partir\s+de\s+agora\s+voce|you\s+are\s+now|"
        r"from\s+now\s+on\s+you|ahora\s+eres|a\s+partir\s+de\s+ahora\s+eres|act\s+as|"
        r"aja\s+como|actue\s+como|actua\s+como|finja\s+ser|pretend\s+to\s+be|roleplay\s+as)\b")),
    # Só formas imperativas que não são substantivos ("venda de 100%" é notícia legítima).
    ("ordem_total", _rx(
        r"\b(compre|comprem|buy|aloque|aloquem|allocate|invista|invistam|vendam|zere|zerem|"
        r"liquide|liquidem)\b\s*(?:[^.;\n]{0,15}?)\b100\s*%"
        r"(?!\s*(de\s+|of\s+|del\s+)?(stake|participac|its\s|the\s|a\s|an\s|da\s+empresa|"
        r"das\s+acoes|do\s+capital))")),
    ("ordem_total_nav", _rx(
        r"\b100\s*%\s*(do|of|del|da)\s+(nav|patrimonio|fundo|fund|portfolio|carteira|cartera)\b")),
    ("ordem_tudo", _rx(
        r"\b(compre|buy|venda|sell|zere|liquide)\s+(tudo|everything|todo|all\s+positions)\b")),
    ("novas_instrucoes", _rx(
        r"\b(novas?\s+instruc(oes|ao)|new\s+instructions?|nuevas?\s+instrucci(ones|on)|"
        r"updated\s+instructions?|instrucoes\s+atualizadas)\b")),
    ("revelar_instrucoes", _rx(
        r"\b(revele|mostre|imprima|repita|reveal|print|show|repeat|muestra|revela|repite)\b"
        r"[^.;\n]{0,30}\b(instrucoes|instructions|prompt|instrucciones|regras|rules|reglas)\b")),
    ("jailbreak", _rx(
        r"\b(jailbreak|dan\s+mode|developer\s+mode|modo\s+desenvolvedor|modo\s+desarrollador|"
        r"sem\s+restricoes|without\s+restrictions|sin\s+restricciones|no\s+restrictions)\b")),
    ("alterar_limites", _rx(
        r"\b(aumente|eleve|remova|desative|desligue|desabilite|ignore|elimine|quite|desactive)\b"
        r"[^.;\n]{0,30}\b(limite|limites|restricao|restricoes|restriccion|restricciones|veto|"
        r"vetos|kill\s*switch|stop\s*loss|compliance)\b")),
    ("alterar_limites_en", _rx(
        r"\b(increase|raise|lift|remove|disable|bypass)\s+(your|all|the\s+fund'?s?|"
        r"the\s+portfolio'?s?|risk)\s+[^.;\n]{0,20}\b(limits?|restrictions?|constraints?|"
        r"vetoe?s?|kill\s*switch)\b")),
    ("exfiltracao", _rx(
        r"\b(send|envie|envia|mande|forward|encaminhe|exfiltre)\b[^.;\n]{0,30}"
        r"\b(e-?mail|api\s*key|chave\s+de\s+api|password|senha|credenciais|credentials|token)\b")),
    ("comando_ao_modelo", _rx(
        r"\b(llm|modelo\s+de\s+linguagem|language\s+model|assistente|assistant|agente\s+de\s+ia|"
        r"ai\s+agent|ai\s+model|modelo\s+de\s+ia|robo)\b[^.;\n]{0,40}"
        r"\b(ignore|aprove|approve|compre|buy|execute|obedeca|obey)\b")),
)
"""Padrões aplicados ao texto normalizado (minúsculas, sem acentos, sem caracteres invisíveis)."""

_COMPACT_KEYWORDS: tuple[str, ...] = (
    "ignoreasregras", "ignoreasinstrucoes", "ignoretodasasregras", "ignoreasregrasanteriores",
    "desconsidereasregras", "ignoreprevious", "ignoreallprevious", "ignorealltheprevious",
    "ignoralasinstrucciones", "ignoralasreglas", "olvidalasinstrucciones", "systemprompt",
    "promptdosistema", "voceagorae", "youarenow", "ahoraeres", "aproveacarteira",
    "approvetheportfolio", "aprobarlacartera", "apruebelacartera", "compre100",
)
"""Palavras-chave procuradas no texto sem espaços/pontuação (pega ofuscação espaçada)."""

_INVISIBLE_CATEGORIES = {"Cf", "Co", "Cn"}
_HTML_COMMENT_RE = _P(r"<!--.*?(-->|$)", re.S)
_SCRIPT_STYLE_RE = _P(r"(?is)<(script|style)\b.*?(</\1\s*>|$)")
_TAG_RE = _P(r"<[^<>]{0,500}>")
_MD_LINK_RE = _P(r"!?\[([^\]\n]{0,300})\]\(([^)\n]{0,500})\)")
_BASE64_LONG_RE = _P(rf"[A-Za-z0-9+/_\-]{{{BASE64_MIN_REMOVE},}}={{0,2}}")
_BASE64_TOKEN_RE = _P(rf"[A-Za-z0-9+/_\-]{{{BASE64_MIN_SCAN},}}={{0,2}}")
_TOKEN_RE = _P(r"\w+")
_WS_RE = _P(r"\s+")
_NON_ALNUM_RE = _P(r"[^0-9a-z]+")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _remove_invisible(text: str) -> tuple[str, bool, bool]:
    """Remove caracteres de formato/invisíveis e de controle; retorna (texto, invis., ctrl.)."""
    out: list[str] = []
    invisible = control = False
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _INVISIBLE_CATEGORIES:
            invisible = True
            continue
        if cat == "Cc":
            if ch not in "\t\n\r":
                control = True
            out.append(" ")
            continue
        out.append(ch)
    return "".join(out), invisible, control


def _normalize_for_scan(text: str) -> str:
    text, _, _ = _remove_invisible(unicodedata.normalize("NFKC", text))
    text = text.translate(_CONFUSABLES)
    text = _strip_accents(text).lower()
    return _WS_RE.sub(" ", text).strip()


def _has_mixed_scripts(text: str) -> bool:
    """Palavra com letras latinas E cirílicas/gregas (assinatura de ataque por homóglifos)."""
    for token in _TOKEN_RE.findall(text):
        latin = other = False
        for ch in token:
            if not ch.isalpha():
                continue
            name = unicodedata.name(ch, "")
            if name.startswith("LATIN"):
                latin = True
            elif name.startswith(("CYRILLIC", "GREEK")):
                other = True
        if latin and other:
            return True
    return False


def _looks_like_base64(token: str) -> bool:
    """Blob com cara de Base64: termina em ``=`` ou mistura maiúsculas, minúsculas e dígitos."""
    if token.endswith("="):
        return True
    return (any(c.isupper() for c in token) and any(c.islower() for c in token)
            and any(c.isdigit() for c in token))


def _decode_base64(token: str) -> str | None:
    """Decodifica um token Base64 (padrão ou URL-safe) se resultar em texto legível."""
    raw = token.strip("=")
    padded = raw + "=" * (-len(raw) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            data = decoder(padded.encode("ascii"))
        except (binascii.Error, ValueError):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        printable = sum(ch.isprintable() or ch.isspace() for ch in text)
        if text and printable / len(text) > 0.9 and any(ch.isalpha() for ch in text):
            return text
    return None


def _scan_patterns(normalized: str) -> list[str]:
    hits = [name for name, rx in INJECTION_PATTERNS if rx.search(normalized)]
    compact = _NON_ALNUM_RE.sub("", normalized)
    leet = _NON_ALNUM_RE.sub("", normalized.translate(_LEET))
    if any(k in compact or k in leet for k in _COMPACT_KEYWORDS) and not hits:
        hits.append("ofuscacao_espacada")
    return hits


def detect_injection(text: str) -> list[str]:
    """Nomes dos padrões de injeção encontrados (vazio se nenhum). Nunca levanta exceção.

    Inspeciona o texto bruto (com entidades HTML resolvidas), o conteúdo de comentários HTML,
    a versão percent-decodificada, tokens Base64 decodificados e a versão sem homóglifos.
    """
    try:
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        unescaped = html.unescape(text)
        variants = [unescaped, urllib.parse.unquote(unescaped)]
        variants += [m.group(0) for m in _HTML_COMMENT_RE.finditer(unescaped)]
        hits: list[str] = []
        for variant in variants:
            hits += _scan_patterns(_normalize_for_scan(variant))
        for m in _BASE64_TOKEN_RE.finditer(unescaped):
            token = m.group(0)
            if token.isalpha() and (token.islower() or token.isupper()):
                continue  # palavra comum, não Base64
            decoded = _decode_base64(token)
            if decoded:
                inner = _scan_patterns(_normalize_for_scan(decoded))
                if inner:
                    hits += ["codificada_base64"] + inner
        if _has_mixed_scripts(unescaped):
            hits.append("homoglifos_escrita_mista")
        return sorted(set(hits))
    except Exception:  # noqa: BLE001 — guardrail nunca pode derrubar o pipeline
        return ["erro_na_inspecao"]


def sanitize_untrusted(text: object, max_len: int = DEFAULT_MAX_LEN) -> tuple[str, list[str]]:
    """Limpa conteúdo não confiável para uso como DADO em prompts e exibição.

    Passos: resolve entidades HTML; remove comentários HTML, ``<script>/<style>``, tags e
    caracteres invisíveis/bidi/de controle; troca links Markdown pelo texto (descarta a URL);
    remove blobs Base64 > 80 caracteres; neutraliza placeholders ``{{…}}``; normaliza espaços
    e trunca em ``max_len``. Retorna ``(texto_limpo, flags)``; flags de injeção começam com
    ``injecao:``. Nunca levanta exceção (falha interna ⇒ texto vazio e flag de injeção).
    """
    try:
        if text is None:
            return "", []
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        elif not isinstance(text, str):
            text = str(text)
        flags: set[str] = set()
        injections = detect_injection(text)

        s = html.unescape(unicodedata.normalize("NFKC", text))
        if _HTML_COMMENT_RE.search(s):
            flags.add("comentario_html")
            s = _HTML_COMMENT_RE.sub(" ", s)
        if _SCRIPT_STYLE_RE.search(s):
            flags.add("html")
            s = _SCRIPT_STYLE_RE.sub(" ", s)
        if _TAG_RE.search(s):
            flags.add("html")
            s = _TAG_RE.sub(" ", s)
        if "<" in s or ">" in s:
            flags.add("html")
            s = s.replace("<", " ").replace(">", " ")
        s, invisible, control = _remove_invisible(s)
        if invisible:
            flags.add("caracteres_invisiveis")
        if control:
            flags.add("caracteres_controle")
        if _MD_LINK_RE.search(s):
            flags.add("link_markdown")
            s = _MD_LINK_RE.sub(lambda m: m.group(1), s)
        def _drop_b64(m: re.Match[str]) -> str:
            if not _looks_like_base64(m.group(0)):
                return m.group(0)
            flags.add("base64")
            return " [base64 removido] "

        s = _BASE64_LONG_RE.sub(_drop_b64, s)
        if "{{" in s or "}}" in s:
            flags.add("placeholder_em_texto_externo")
            s = s.replace("{{", "{ {").replace("}}", "} }")
        s = _WS_RE.sub(" ", s).strip()
        if max_len > 0 and len(s) > max_len:
            flags.add("truncado")
            s = s[: max(0, max_len - 1)].rstrip() + "…"
        flags.update(f"{INJECTION_FLAG_PREFIX}{name}" for name in injections)
        return s, sorted(flags)
    except Exception:  # noqa: BLE001
        return "", [f"{INJECTION_FLAG_PREFIX}erro_sanitizacao"]


def is_injection_flagged(flags: Iterable[str]) -> bool:
    return any(f.startswith(INJECTION_FLAG_PREFIX) for f in flags)


# ==========================================================
# Números livres e placeholders
# ==========================================================

PLACEHOLDER_RE = _P(r"\{\{\s*fact:([^}\s]+)\s*\}\}")
_MONTHS_PT_ES = (
    "janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|"
    "dezembro|enero|febrero|marzo|mayo|junio|julio|septiembre|setiembre|octubre|noviembre|"
    "diciembre"
)
_MONTHS_EN = ("january|february|march|april|may|june|july|august|september|october|november|"
              "december")
_NOT_QUANTITY = r"(?!\s?%|\s?p\.p\.|[.,]\d|\s?[xX]\b)"
"""Uma data/rótulo nunca é seguido de ``%``, ``p.p.``, casa decimal ou ``x`` (senão é número)."""
_ALLOWED_NUMERIC_RES: tuple[re.Pattern[str], ...] = (
    # Datas ISO (com hora opcional) e dd/mm/aaaa.
    _P(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
       + _NOT_QUANTITY),
    _P(r"\b\d{1,2}/\d{1,2}/\d{4}\b" + _NOT_QUANTITY),
    # "25 de outubro", "25 de octubre", "October 25", "25th of October".
    _P(rf"(?i)\b\d{{1,2}}(?:º|o)?\s+de\s+(?:{_MONTHS_PT_ES})\b"),
    _P(rf"(?i)\b(?:{_MONTHS_EN})\s+\d{{1,2}}(?:st|nd|rd|th)?\b{_NOT_QUANTITY}"),
    _P(rf"(?i)\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTHS_EN})\b"),
    # Trimestres/semestres: 3T26, 4Q25, 1S26, 2T2026, Q3 2026, Q3'26, H1 2026, 3º trimestre.
    _P(rf"(?i)\b[1-4]\s?[TQSH]\s?(?:\d{{4}}|\d{{2}})\b{_NOT_QUANTITY}"),
    _P(rf"(?i)\b[QTH][1-4](?:\s?['’]?\s?(?:\d{{4}}|\d{{2}})\b{_NOT_QUANTITY})?\b"),
    _P(r"(?i)\b[1-4](?:º|o|st|nd|rd|th)?\s?(?:tri|trimestre|semestre|quarter|half)\b"),
    _P(rf"(?i)\bFY\s?(?:\d{{4}}|\d{{2}})\b{_NOT_QUANTITY}"),
    # Ordinais (1º, 2ª).
    _P(r"\b\d{1,2}[ºª]"),
)
# Sem lookbehind em "." e ",": ".5x" e ",75%" são números escritos sem o zero inicial.
_NUMBER_RE = _P(r"(?<![\w/])([+\-−]?\d+(?:[.,]\d+)*)(\s?%|\s?p\.p\.|[A-Za-zÀ-ÿ]+)?")
_SPELLED_QUANTITY_RE = _P(
    r"(?i)\b(por\s*cento|por\s*ciento|percent|per\s*cent|pontos?\s+percentuais|"
    r"puntos?\s+porcentuales|percentage\s+points?|pontos?[\s-]+base|puntos?\s+b[aá]sicos|"
    r"basis\s+points?)\b")
"""Quantidades por extenso ("treze por cento"): números também não podem ser escritos assim."""
_YEAR_RE = _P(r"^(?:19|20)\d{2}$")
_UNIT_SUFFIXES = frozenset({
    "x", "bi", "mi", "bn", "mm", "m", "k", "b", "pp", "bp", "bps", "mil", "tri", "pts", "pt",
    "p", "pct", "usd", "brl", "mxn", "clp", "cop", "pen", "ars", "d", "dias", "days", "a",
    "aa", "y", "yr", "yrs", "anos", "meses", "semanas", "w", "mo", "milhoes", "milhões",
    "bilhoes", "bilhões", "millones", "million", "billion", "vezes", "times", "percent",
    "porcento", "porciento", "reais", "dolares", "dólares", "pesos", "bilhao", "bilhão",
    "milhao", "milhão", "trilhoes", "trilhões", "trillion", "thousand",
})


def extract_fact_ids(text: str) -> list[str]:
    """Ids citados em placeholders ``{{fact:<id>}}``, na ordem de aparição (sem repetição)."""
    if not isinstance(text, str):
        return []
    return list(dict.fromkeys(m.group(1) for m in PLACEHOLDER_RE.finditer(text)))


def find_free_numbers(text: str, allowed_terms: Iterable[str] = ()) -> list[str]:
    """Números escritos fora de placeholders (ex.: ``13,75%``, ``2.5x``, ``US$ 12``).

    Permitidos: placeholders ``{{fact:...}}``, datas ISO/dd-mm-aaaa e por extenso, anos
    (1900–2099), rótulos de trimestre/semestre (``3T26``, ``Q3 2026``, ``1S26``), ordinais
    (``1º``) e identificadores alfanuméricos (``PETR4``, ``B3``, ``3R``). ``allowed_terms``
    acrescenta termos literais (ex.: nome do emissor com dígitos).
    """
    if not isinstance(text, str) or not text:
        return []
    s = PLACEHOLDER_RE.sub(" ", text)
    for term in sorted({*DEFAULT_ALLOWED_TERMS, *allowed_terms}, key=len, reverse=True):
        if term and any(ch.isdigit() for ch in term):
            s = re.sub(re.escape(term), " ", s, flags=re.IGNORECASE)
    for rx in _ALLOWED_NUMERIC_RES:
        s = rx.sub(" ", s)
    found: list[str] = []
    for m in _NUMBER_RE.finditer(s):
        number, suffix = m.group(1), m.group(2) or ""
        if suffix and suffix[0].isalpha() and suffix.lower() not in _UNIT_SUFFIXES:
            continue  # identificador alfanumérico (ticker, nome), não quantidade
        if not suffix and number[0] not in "+-−" and _YEAR_RE.match(number):
            continue
        found.append(f"{number}{suffix}".strip())
    found += [m.group(0) for m in _SPELLED_QUANTITY_RE.finditer(s)]
    return found


_MARKUP_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("link_markdown", _P(r"!?\[[^\]\n]*\]\s*\([^)\n]*\)")),
    ("referencia_markdown", _P(r"(?m)^\s*\[[^\]\n]+\]:\s*\S+")),
    ("url", _P(r"(?i)\b(?:https?|ftp|file|javascript|data|vbscript|mailto)\s*:|\bwww\.")),
    ("html", _P(r"<(?:/?[A-Za-z][\w:-]*(?:\s[^<>]*)?/?>|!--)")),
)
"""Marcação proibida em texto livre de modelo: links/imagens (exfiltração ao renderizar),
URLs e HTML. Fontes externas entram só como evidência (``EvidenceRef``), nunca no texto."""


def find_markup(text: str) -> list[str]:
    """Tipos de marcação proibida encontrados no texto livre (vazio se nenhum)."""
    if not isinstance(text, str) or not text:
        return []
    return [name for name, rx in _MARKUP_RES if rx.search(text)]


def malformed_placeholders(text: str) -> list[str]:
    """Trechos de placeholder mal formados (``{{ fact: x }}``, ``{{fact:x}``, ``{fact:x}``).

    Um placeholder inválido não seria renderizado e apareceria cru ao gestor.
    """
    if not isinstance(text, str) or not text:
        return []
    rest = PLACEHOLDER_RE.sub(" ", text)
    bad = [m.group(0) for m in _P(r"\{\{[^{}]{0,80}\}?\}?|\}\}|\{\s*fact\s*:[^}]{0,80}\}?",
                                  re.I).finditer(rest)]
    return list(dict.fromkeys(b.strip() for b in bad))


def text_format_issues(path: str, text: str) -> list[str]:
    """Problemas de forma do texto livre (marcação/URL e placeholders mal formados)."""
    issues: list[str] = []
    markup = find_markup(text)
    if markup:
        issues.append(f"{path}: marcação/URL não permitida em texto livre {markup}")
    bad = malformed_placeholders(text)
    if bad:
        issues.append(f"{path}: {len(bad)} placeholder(s) mal formado(s)")
    return issues


def check_placeholders(text: str, factbook: FactBook) -> list[str]:
    """Ids de placeholders que NÃO existem no FactBook."""
    return [fid for fid in extract_fact_ids(text) if fid not in factbook.facts]


def render_placeholders(text: str, factbook: FactBook, mark_calculated: bool = False) -> str:
    """Substitui ``{{fact:id}}`` pelo valor formatado; id inexistente ⇒ ``[fato inexistente]``.

    ``mark_calculated`` acrescenta ``[Calculado]`` após cada valor (rótulo de procedência).
    """
    if not isinstance(text, str):
        return ""

    def _sub(m: re.Match[str]) -> str:
        fact = factbook.facts.get(m.group(1))
        if fact is None:
            return UNKNOWN_FACT_TEXT
        return f"{fact.formatted} [Calculado]" if mark_calculated else fact.formatted

    return PLACEHOLDER_RE.sub(_sub, text)


def mask_digits(text: str) -> str:
    """Troca dígitos por ``#`` (para exibir diagnósticos sem propagar números não verificados)."""
    return re.sub(r"\d", "#", text)


# ==========================================================
# Verificação das saídas dos agentes
# ==========================================================

def _as_date(value: date | datetime | str) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _text_issues(path: str, text: str, factbook: FactBook, *, cited: set[str] | None,
                 issuer_id: str | None, allowed_terms: Iterable[str]) -> list[str]:
    issues: list[str] = []
    nums = find_free_numbers(text, allowed_terms)
    if nums:
        issues.append(f"{path}: número não autorizado fora de placeholder {nums}")
    unknown = check_placeholders(text, factbook)
    if unknown:
        issues.append(f"{path}: fato inexistente no FactBook {unknown}")
    known = [f for f in extract_fact_ids(text) if f in factbook.facts]
    if issuer_id is not None:
        foreign = [f for f in known if factbook.facts[f].issuer_id not in (None, issuer_id)]
        if foreign:
            issues.append(f"{path}: fato de outro emissor {foreign}")
    if cited is not None:
        uncited = [f for f in known if f not in cited]
        if uncited:
            issues.append(f"{path}: fato usado no texto sem citação como evidência {uncited}")
    issues += text_format_issues(path, text)
    inj = detect_injection(text)
    if inj:
        issues.append(f"{path}: padrão de injeção na saída do modelo {inj}")
    return issues


def _evidence_issues(path: str, ids: Iterable[str], valid: set[str], as_of: date,
                     evidence_dates: Mapping[str, date | datetime | str] | None,
                     required: bool = True) -> list[str]:
    ids = list(ids)
    issues: list[str] = []
    if required and not ids:
        issues.append(f"{path}: afirmação sem evidência")
    invalid = [i for i in ids if i not in valid]
    if invalid:
        issues.append(f"{path}: evidência inexistente no pacote da semana {invalid}")
    if evidence_dates:
        late = [i for i in ids if i in evidence_dates
                and (d := _as_date(evidence_dates[i])) is not None and d > as_of]
        if late:
            issues.append(f"{path}: evidência publicada após {as_of.isoformat()} (look-ahead) {late}")
    return issues


def _norm_quote(text: str) -> str:
    return _WS_RE.sub(" ", _strip_accents(text).lower()).strip()


def verify_analyst_output(out: AnalystOutput, factbook: FactBook, valid_evidence_ids: set[str],
                          as_of: date, *,
                          evidence_dates: Mapping[str, date | datetime | str] | None = None,
                          evidence_texts: Mapping[str, str] | None = None,
                          issuer_id: str | None = None,
                          allowed_terms: Iterable[str] = ()) -> list[str]:
    """Problemas de uma saída do analista (lista vazia = aprovada pelo verificador)."""
    issues: list[str] = []
    cited = {e for d in [*out.drivers, *out.risks] for e in d.evidence_ids}
    for path, text in output_texts(out):
        issues += _text_issues(path, text, factbook, cited=cited, issuer_id=issuer_id,
                               allowed_terms=allowed_terms)
    for i, d in enumerate(out.drivers):
        issues += _evidence_issues(f"drivers[{i}]", d.evidence_ids, valid_evidence_ids, as_of,
                                   evidence_dates)
    for i, d in enumerate(out.risks):
        issues += _evidence_issues(f"risks[{i}]", d.evidence_ids, valid_evidence_ids, as_of,
                                   evidence_dates)
    for i, c in enumerate(out.citations):
        issues += _evidence_issues(f"citations[{i}]", [c.evidence_id], valid_evidence_ids, as_of,
                                   evidence_dates)
        if c.quote:
            source = (evidence_texts or {}).get(c.evidence_id)
            if source is None or _norm_quote(c.quote) not in _norm_quote(source):
                issues.append(f"citations[{i}]: trecho citado não encontrado na evidência "
                              f"{c.evidence_id!r}")
    if out.abstain and out.stance != 0:
        issues.append("abstenção com stance diferente de zero")
    if not out.abstain and out.stance != 0 and not out.drivers:
        issues.append("stance direcional sem nenhum driver com evidência")
    if out.stance > 0 and out.p_outperform < 0.5:
        issues.append("stance positiva com probabilidade de superar < 0,5")
    if out.stance < 0 and out.p_outperform > 0.5:
        issues.append("stance negativa com probabilidade de superar > 0,5")
    return issues


def verify_short_risk_output(out: ShortRiskOutput, factbook: FactBook,
                             valid_evidence_ids: set[str], as_of: date, *,
                             evidence_dates: Mapping[str, date | datetime | str] | None = None,
                             issuer_id: str | None = None,
                             allowed_terms: Iterable[str] = ()) -> list[str]:
    issues: list[str] = []
    cited = set(out.evidence_ids)
    for path, text in output_texts(out):
        issues += _text_issues(path, text, factbook, cited=cited, issuer_id=issuer_id,
                               allowed_terms=allowed_terms)
    issues += _evidence_issues("evidence_ids", out.evidence_ids, valid_evidence_ids, as_of,
                               evidence_dates)
    return issues


def verify_macro_output(out: MacroOutput, factbook: FactBook, valid_evidence_ids: set[str],
                        as_of: date, *, scope: str | None = None,
                        evidence_dates: Mapping[str, date | datetime | str] | None = None,
                        allowed_terms: Iterable[str] = ()) -> list[str]:
    issues: list[str] = []
    if scope is not None and out.scope.strip().upper() != scope.strip().upper():
        issues.append(f"escopo divergente: pedido {scope!r}, recebido {out.scope!r}")
    cited = set(out.evidence_ids)
    for path, text in output_texts(out):
        issues += _text_issues(path, text, factbook, cited=cited, issuer_id=None,
                               allowed_terms=allowed_terms)
    issues += _evidence_issues("evidence_ids", out.evidence_ids, valid_evidence_ids, as_of,
                               evidence_dates, required=out.stance != 0)
    return issues


def verify_news_output(out: NewsOutput, expected: Mapping[str, str]) -> list[str]:
    """``expected``: news_id → issuer_id esperado. Exige cobertura exata, sem duplicatas."""
    issues: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(out.items):
        if item.news_id not in expected:
            issues.append(f"items[{i}]: notícia fora do pacote {item.news_id!r}")
            continue
        if item.news_id in seen:
            issues.append(f"items[{i}]: notícia duplicada {item.news_id!r}")
        seen.add(item.news_id)
        if item.issuer_id != expected[item.news_id]:
            issues.append(f"items[{i}]: emissor divergente para {item.news_id!r}")
    missing = sorted(set(expected) - seen)
    if missing:
        issues.append(f"notícias sem avaliação {missing}")
    return issues


def verify_debate_output(out: DebateOutput, factbook: FactBook, valid_evidence_ids: set[str],
                         as_of: date, *, side: str, issuer_id: str | None = None,
                         evidence_dates: Mapping[str, date | datetime | str] | None = None,
                         allowed_terms: Iterable[str] = ()) -> list[str]:
    issues: list[str] = []
    if out.side != side:
        issues.append(f"lado divergente: pedido {side!r}, recebido {out.side!r}")
    for i, arg in enumerate(out.arguments):
        issues += _text_issues(f"arguments[{i}]", arg.text, factbook,
                               cited=set(arg.evidence_ids), issuer_id=issuer_id,
                               allowed_terms=allowed_terms)
        issues += _evidence_issues(f"arguments[{i}]", arg.evidence_ids, valid_evidence_ids,
                                   as_of, evidence_dates)
    return issues


def verify_judge_output(out: JudgeOutput, factbook: FactBook, valid_evidence_ids: set[str],
                        as_of: date, *, prior_evidence_ids: set[str],
                        issuer_id: str | None = None,
                        evidence_dates: Mapping[str, date | datetime | str] | None = None,
                        allowed_terms: Iterable[str] = ()) -> list[str]:
    issues: list[str] = []
    cited = set(out.new_evidence_ids) | set(prior_evidence_ids)
    for path, text in output_texts(out):
        issues += _text_issues(path, text, factbook, cited=cited, issuer_id=issuer_id,
                               allowed_terms=allowed_terms)
    issues += _evidence_issues("new_evidence_ids", out.new_evidence_ids, valid_evidence_ids,
                               as_of, evidence_dates, required=False)
    if out.stance_change != 0:
        new = [e for e in out.new_evidence_ids
               if e in valid_evidence_ids and e not in prior_evidence_ids]
        if not new:
            issues.append("mudança de stance sem evidência nova válida")
    return issues


def verify_output(out: BaseModel, **kwargs: object) -> list[str]:
    """Despacho genérico (usado na avaliação do golden set)."""
    dispatch = {
        AnalystOutput: verify_analyst_output, ShortRiskOutput: verify_short_risk_output,
        MacroOutput: verify_macro_output, DebateOutput: verify_debate_output,
        JudgeOutput: verify_judge_output,
    }
    if isinstance(out, NewsOutput):
        return verify_news_output(out, kwargs["expected"])  # type: ignore[arg-type]
    fn = dispatch.get(type(out))
    if fn is None:
        return [f"schema sem verificador: {type(out).__name__}"]
    return fn(out, **kwargs)  # type: ignore[operator]


def defuse_for_display(text: str, max_len: int = 400) -> str:
    """Diagnóstico seguro para exibição (memo/app): dígitos mascarados e marcação desarmada.

    Mensagens de verificação e de erro ecoam strings controladas pelo modelo (ids de evidência
    inválidos, nomes de chaves extras, trechos de placeholder); colchetes, sinais de tag e
    esquemas de URL são trocados por equivalentes inertes para que nada vire link, imagem ou
    HTML ao renderizar Markdown.
    """
    out = mask_digits(str(text))
    for a, b in (("[", "⟦"), ("]", "⟧"), ("<", "‹"), (">", "›"), ("://", "∶//"),
                 ("www.", "www․"), ("`", "'")):
        out = out.replace(a, b)
    out = re.sub(r"(?i)\b(javascript|data|vbscript|file|mailto)\s*:", r"\1∶", out)
    return out if len(out) <= max_len else out[: max_len - 1] + "…"


def verifier_messages(issues: Iterable[str]) -> list[str]:
    """Diagnósticos para exibição em notas: prefixo ``VERIFICADOR:``, dígitos mascarados e
    marcação desarmada (ver :func:`defuse_for_display`)."""
    return [f"{VERIFIER_PREFIX} {defuse_for_display(i)}" for i in issues]


# ==========================================================
# Kill switch da IA (modo "somente quant")
# ==========================================================

def ai_kill_switch(notes_issues_rate: float, provider_failed: bool, injection_confirmed: bool,
                   eval_regressed: bool,
                   threshold: float = KILL_SWITCH_ISSUE_RATE) -> tuple[bool, str]:
    """Decide se a camada de IA deve ser desligada nesta semana.

    Gatilhos (docs/research/07 §6.6): mais de ``threshold`` das notas com falha em gate
    determinístico, indisponibilidade do provedor, injeção confirmada (padrão de injeção na
    saída do modelo) ou regressão no golden set. Retorna ``(desligar, motivo)``.
    """
    reasons = []
    rate = float(notes_issues_rate) if notes_issues_rate == notes_issues_rate else 1.0
    if rate > threshold:
        reasons.append(f"{rate:.1%} das notas falharam nos gates determinísticos "
                       f"(limite {threshold:.0%})")
    if provider_failed:
        reasons.append("provedor de IA indisponível ou com falhas generalizadas")
    if injection_confirmed:
        reasons.append("injeção de instruções confirmada em saída do modelo")
    if eval_regressed:
        reasons.append("regressão no golden set de avaliação")
    if not reasons:
        return False, "IA ativa: nenhum gatilho de desligamento."
    return True, "IA DESATIVADA (modo somente quant): " + "; ".join(reasons) + "."
