"""Manchetes por emissor via Google News RSS — conteúdo NÃO CONFIÁVEL.

- Consulta = nome do emissor (sem parênteses) + ticker local primário (raiz sem sufixo), com o
  operador ``when:<N>d``. Idioma pelo país: ``pt-BR`` (BR), ``es-419`` (demais) e ``en-US``
  para emissores cuja linha primária é listada nos EUA (``US_LISTED``).
- Cada item vira ``NewsItem(untrusted=True)`` com ``news_id = 'rss_' + sha256(link)[:12]``
  (determinístico). Títulos passam por ``research.guardrails.sanitize_untrusted`` quando o
  módulo existe; senão, por um sanitizador mínimo local (remove HTML/caracteres de controle,
  normaliza espaços e trunca em 300 caracteres). Instruções embutidas em manchetes ("ignore as
  regras…") nunca são executadas: são apenas dados citáveis.
- Janela: ``[as_of - lookback_days, as_of 23:59:59 no fuso do país]``; itens com data posterior
  (futuros em relação a ``as_of``) são EXCLUÍDOS — sem look-ahead.
- Deduplicação por ``news_id`` (o mesmo link para vários emissores une ``issuer_ids``) e por
  (título normalizado, fonte).
"""

from __future__ import annotations

import hashlib
import html
import importlib
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..contracts import NewsItem
from ..universe import Universe
from .yahoo import MAX_WORKERS, FetchError, Sleeper, http_request

log = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
MAX_TITLE_LEN = 300
SOURCE_NAME = "Google News RSS"

# país -> (hl, gl, ceid, idioma do NewsItem, fuso local do pregão)
_LOCALE: dict[str, tuple[str, str, str, str, str]] = {
    "BR": ("pt-BR", "BR", "BR:pt-419", "pt", "America/Sao_Paulo"),
    "MX": ("es-419", "MX", "MX:es-419", "es", "America/Mexico_City"),
    "CL": ("es-419", "CL", "CL:es-419", "es", "America/Santiago"),
    "CO": ("es-419", "CO", "CO:es-419", "es", "America/Bogota"),
    "PE": ("es-419", "PE", "PE:es-419", "es", "America/Lima"),
    "AR": ("es-419", "AR", "AR:es-419", "es", "America/Argentina/Buenos_Aires"),
    "PA": ("es-419", "PA", "PA:es-419", "es", "America/Panama"),
    "UY": ("es-419", "UY", "UY:es-419", "es", "America/Montevideo"),
    "LATAM": ("es-419", "US", "US:es-419", "es", "America/New_York"),
}
_US_LOCALE = ("en-US", "US", "US:en", "en", "America/New_York")

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏"
                      r"‪-‮⁠-⁤﻿]")
_WS_RE = re.compile(r"\s+")
_SUFFIX_RE = re.compile(r"\.(SA|MX|SN|CL|LM|BA)$", re.IGNORECASE)


@dataclass(frozen=True)
class NewsQuery:
    """Consulta de notícias de um emissor."""

    issuer_id: str
    issuer_name: str
    ticker: str          # raiz do ticker local primário (ou da linha nos EUA)
    country: str
    us_listed: bool = False

    @property
    def locale(self) -> tuple[str, str, str, str, str]:
        return _US_LOCALE if self.us_listed else _LOCALE.get(self.country, _LOCALE["LATAM"])

    def query_text(self, lookback_days: int) -> str:
        name = clean_issuer_name(self.issuer_name)
        return f"{name} {self.ticker} when:{int(lookback_days)}d".strip()


def clean_issuer_name(name: str) -> str:
    return _WS_RE.sub(" ", re.sub(r"\([^)]*\)", " ", name)).strip()


def news_id_for(link: str) -> str:
    return "rss_" + hashlib.sha256(link.strip().encode("utf-8")).hexdigest()[:12]


def _local_sanitize(text: str, max_len: int = MAX_TITLE_LEN) -> str:
    t = html.unescape(str(text))
    t = _TAG_RE.sub(" ", t)
    t = _CTRL_RE.sub("", t)
    t = unicodedata.normalize("NFC", t)
    t = _WS_RE.sub(" ", t).strip()
    return t[:max_len].rstrip()


def _resolve_sanitizer() -> Callable[[str], str]:
    try:
        mod = importlib.import_module("..research.guardrails", package=__package__)
        fn = getattr(mod, "sanitize_untrusted", None)
    except ImportError:
        fn = None
    if fn is None:
        return _local_sanitize

    def wrapped(text: str) -> str:
        try:
            out = fn(text)
        except Exception:
            return _local_sanitize(text)
        if isinstance(out, tuple):
            out = out[0]
        # Garantias mínimas mesmo que o sanitizador externo mude.
        return _local_sanitize(str(out))

    return wrapped


def sanitize_title(text: str) -> str:
    """Sanitiza um título não confiável (guardrails do pacote quando disponível)."""
    return _resolve_sanitizer()(text)


def queries_from_universe(universe: Universe, issuer_ids: Iterable[str] | None = None
                          ) -> list[NewsQuery]:
    """Monta as consultas por emissor a partir do universo (ordem determinística)."""
    ids = sorted(issuer_ids) if issuer_ids is not None else sorted(universe.issuers.index)
    out: list[NewsQuery] = []
    for iid in ids:
        if iid not in universe.issuers.index:
            continue
        row = universe.issuers.loc[iid]
        lines = universe.lines_for(iid)
        primary = str(row["primary_ticker"])
        locals_ = lines[lines["line_type"] == "LOCAL"]
        if primary in locals_.index:
            tkr = primary
        elif not locals_.empty:
            tkr = str(sorted(locals_.index)[0])
        else:
            tkr = primary
        out.append(NewsQuery(issuer_id=str(iid), issuer_name=str(row["issuer_name"]),
                             ticker=_SUFFIX_RE.sub("", tkr), country=str(row["country"]),
                             us_listed=str(row["primary_line_type"]) == "US_LISTED"))
    return out


def _norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def parse_rss(content: bytes | str) -> list[dict[str, Any]]:
    """Itens do RSS: ``title, link, source, published_at`` (UTC, tz-aware)."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FetchError(f"RSS inválido: {exc}") from exc
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        if not title or not link or not pub:
            continue
        try:
            dt = parsedate_to_datetime(pub)
        except (TypeError, ValueError, IndexError):
            continue
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")].rstrip()
        items.append({"title": title, "link": link, "source": source,
                      "published_at": dt.astimezone(UTC)})
    return items


def window_bounds(as_of: date, lookback_days: int, tz_name: str) -> tuple[datetime, datetime]:
    """Janela ``[início do dia (as_of - lookback), as_of 23:59:59]`` no fuso local, em UTC."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(as_of - timedelta(days=int(lookback_days)), dtime(0, 0), tzinfo=tz)
    end = datetime.combine(as_of, dtime(23, 59, 59), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def fetch_issuer_news(query: NewsQuery, as_of: date, lookback_days: int, *,
                      session: Any | None = None, sleep: Sleeper = time.sleep,
                      sanitizer: Callable[[str], str] | None = None) -> list[NewsItem]:
    """Manchetes de um emissor dentro da janela (sem itens futuros)."""
    hl, gl, ceid, lang, tz_name = query.locale
    resp = http_request("GET", GOOGLE_NEWS_RSS, session=session, sleep=sleep,
                        params={"q": query.query_text(lookback_days), "hl": hl, "gl": gl,
                                "ceid": ceid})
    if resp.status_code != 200:
        raise FetchError(f"Google News RSS HTTP {resp.status_code} ({query.issuer_id})")
    lo, hi = window_bounds(as_of, lookback_days, tz_name)
    san = sanitizer or _resolve_sanitizer()
    out = []
    for it in parse_rss(resp.content):
        if not (lo <= it["published_at"] <= hi):
            continue
        title = san(it["title"])
        if not title:
            continue
        out.append(NewsItem(news_id=news_id_for(it["link"]), issuer_ids=[query.issuer_id],
                            title=title, source=san(it["source"])[:120], url=it["link"],
                            published_at=it["published_at"], language=lang, is_synthetic=False))
    return out


def dedupe_news(items: Iterable[NewsItem]) -> list[NewsItem]:
    """Remove duplicatas (mesmo link ou mesmo título normalizado + fonte), unindo emissores."""
    by_id: dict[str, NewsItem] = {}
    for it in items:
        prev = by_id.get(it.news_id)
        if prev is None:
            by_id[it.news_id] = it
        else:
            ids = sorted(set(prev.issuer_ids) | set(it.issuer_ids))
            first = min((prev, it), key=lambda n: (n.published_at, n.title))
            by_id[it.news_id] = first.model_copy(update={"issuer_ids": ids})
    by_key: dict[tuple[str, str], NewsItem] = {}
    for it in sorted(by_id.values(), key=lambda n: (n.published_at, n.news_id)):
        key = (_norm_title(it.title), it.source.strip().lower())
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = it
        else:
            ids = sorted(set(prev.issuer_ids) | set(it.issuer_ids))
            by_key[key] = prev.model_copy(update={"issuer_ids": ids})
    return sorted(by_key.values(), key=lambda n: (n.published_at, n.news_id))


def fetch_news(queries: Sequence[NewsQuery], as_of: date, lookback_days: int = 14, *,
               session: Any | None = None, max_workers: int = MAX_WORKERS,
               sleep: Sleeper = time.sleep) -> tuple[list[NewsItem], list[str]]:
    """Notícias de vários emissores (<= 8 threads). Devolve ``(itens, emissores_com_falha)``.

    Se TODAS as consultas falharem, levanta :class:`FetchError` (fonte indisponível).
    """
    san = _resolve_sanitizer()

    def one(q: NewsQuery) -> tuple[str, list[NewsItem] | None]:
        try:
            return q.issuer_id, fetch_issuer_news(q, as_of, lookback_days, session=session,
                                                  sleep=sleep, sanitizer=san)
        except Exception as exc:
            log.warning("Notícias indisponíveis para %s: %r", q.issuer_id, exc)
            return q.issuer_id, None

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, max_workers))) as ex:
        results = list(ex.map(one, list(queries)))
    failed = sorted(i for i, r in results if r is None)
    if queries and len(failed) == len(queries):
        raise FetchError("Google News RSS indisponível para todos os emissores.")
    items = [n for _, r in results if r for n in r]
    return dedupe_news(items), failed
