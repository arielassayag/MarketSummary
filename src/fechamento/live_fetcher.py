"""Coleta pública, sujeita a atraso e indisponibilidade, sem substituir fatos ausentes."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
MARKET_TZ = ZoneInfo("America/Sao_Paulo")


def compute_sha256(filepath: Path) -> str:
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _positive(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Preço/taxa ausente, não finito ou não positivo")
    return number


def fetch_brasilapi_taxas() -> dict[str, float]:
    """Obtém taxas da BrasilAPI; uma falha nunca vira uma taxa fixa."""
    try:
        data = _get_json("https://brasilapi.com.br/api/taxas/v1")
        taxas = {item["nome"].upper(): _positive(item["valor"]) for item in data}
        for required in ("SELIC", "CDI"):
            if required not in taxas:
                raise ValueError(f"Taxa {required} ausente")
        return taxas
    except Exception as exc:
        raise RuntimeError(f"BrasilAPI: taxas indisponíveis ({exc}).") from exc


def fetch_awesomeapi_usd_brl() -> dict[str, Any]:
    """Obtém bid e timestamp da fonte; a referência cambial é definida pela AwesomeAPI."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL"
    try:
        usd = _get_json(url)["USDBRL"]
        current = _positive(usd["bid"])
        variation = float(usd["varBid"])
        previous = _positive(current - variation)
        if usd.get("timestamp"):
            observed = datetime.fromtimestamp(int(usd["timestamp"]), UTC)
        else:
            observed = datetime.fromisoformat(usd["create_date"]).replace(tzinfo=MARKET_TZ).astimezone(UTC)
        return {
            "ticker": "USD/BRL", "current_price": current, "previous_price": previous,
            "pct_change": current / previous - 1,
            "high": _positive(usd["high"]), "low": _positive(usd["low"]),
            "timestamp": observed.isoformat(), "observed_at": observed.isoformat(),
            "reference_date": observed.astimezone(MARKET_TZ).date().isoformat(),
            "source_url": url,
        }
    except Exception as exc:
        raise RuntimeError(f"AwesomeAPI: câmbio indisponível ({exc}).") from exc


def fetch_yahoo_chart(ticker: str) -> dict[str, Any]:
    """Usa o último preço e o fechamento da sessão anterior, nunca o início do range."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker, safe='')}?interval=1d&range=5d"
    try:
        result = _get_json(url)["chart"]["result"][0]
        meta = result["meta"]
        observed = datetime.fromtimestamp(int(meta["regularMarketTime"]), UTC)
        session = observed.astimezone(MARKET_TZ).date()
        bars = result["indicators"]["quote"][0]["close"]
        history = []
        for timestamp, close in zip(result["timestamp"], bars, strict=True):
            day = datetime.fromtimestamp(timestamp, MARKET_TZ).date()
            if day < session:
                # Não pula uma sessão com fechamento ausente para calcular um retorno de vários dias.
                history.append((day, close))
        if not history:
            raise ValueError("Fechamento da sessão anterior ausente na série diária")
        previous_session, close = max(history, key=lambda row: row[0])
        return {
            "ticker": ticker.replace(".SA", "").replace("^BVSP", "IBOV"),
            "current_price": _positive(meta["regularMarketPrice"]),
            "previous_price": _positive(close), "currency": meta["currency"],
            "observed_at": observed.isoformat(), "reference_date": session.isoformat(),
            "previous_session": previous_session.isoformat(), "source_url": url,
        }
    except Exception as exc:
        raise RuntimeError(f"Yahoo Finance: cotação de {ticker} indisponível ({exc}).") from exc


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


TICKER_NEWS_ALIASES = {
    "PETR4": ("PETR4", "PETROBRAS"),
    "VALE3": ("VALE3", "VALE"),
    "ITUB4": ("ITUB4", "ITAÚ", "ITAU", "ITAÚ UNIBANCO", "ITAU UNIBANCO"),
    "BBDC4": ("BBDC4", "BRADESCO"),
    "BBAS3": ("BBAS3", "BANCO DO BRASIL"),
    "WEGE3": ("WEGE3", "WEG"),
    "IBOV": ("IBOV", "IBOVESPA", "B3", "BOLSA"),
    "USD/BRL": ("USD/BRL", "DÓLAR", "DOLAR", "CÂMBIO", "CAMBIO"),
}


def _news_id(prefix: str, title: str, link: str) -> str:
    digest = hashlib.sha256(f"{title}|{link}".encode()).hexdigest()[:12]
    return f"news_{prefix}_{digest}"


def _related_tickers(title: str) -> list[str]:
    normalized = title.upper()
    related = [
        ticker
        for ticker, aliases in TICKER_NEWS_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized) for alias in aliases)
    ]
    return related


def _parse_gdelt_date(raw: str) -> str:
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Data inválida retornada pela GDELT: {raw!r}")


def build_market_news_query(tickers: list[str] | None = None) -> str:
    """Monta uma consulta GDELT com empresas da carteira e filtros de imprensa local."""
    clean_tickers = [ticker.replace(".SA", "") for ticker in (tickers or [])]
    terms = ["Ibovespa"]
    for ticker in clean_tickers:
        aliases = TICKER_NEWS_ALIASES.get(ticker, (ticker,))
        company_alias = next((alias for alias in aliases if alias != ticker), ticker)
        terms.append(f'"{company_alias}"' if " " in company_alias else company_alias)
    unique_terms = list(dict.fromkeys(terms))
    return f"({' OR '.join(unique_terms)}) sourcelang:portuguese sourcecountry:brazil"


def fetch_gdelt_market_news(
    query: str,
    max_items: int = 6,
    timespan: str = "24h",
) -> list[dict[str, Any]]:
    """Busca manchetes pela API JSON pública da GDELT DOC 2.0, sem chave."""
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "DateDesc",
        "timespan": timespan,
        "maxrecords": str(max(1, min(max_items, 250))),
    }
    url = f"{GDELT_DOC_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    if not isinstance(articles, list):
        return []
    news_list: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        required = [article.get(k) for k in ("title", "url", "seendate")]
        if any(type(value) is not str for value in required):
            continue
        title = html.unescape(article["title"].strip())
        link = article["url"].strip()
        published_raw = article["seendate"].strip()
        domain_raw = article.get("domain")
        if domain_raw is not None and type(domain_raw) is not str:
            continue
        if not title or not link or not published_raw:
            continue
        dedupe_key = f"{title.casefold()}|{link}"
        if dedupe_key in seen:
            continue
        try:
            parsed_url = urllib.parse.urlsplit(link)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                continue
            _ = parsed_url.port  # recusa porta/autoridade malformada sem abortar os outros registros
            observed_at = _parse_gdelt_date(published_raw)
        except ValueError:
            continue
        seen.add(dedupe_key)
        domain = (domain_raw or "").strip() or parsed_url.netloc
        source = domain.replace(".", "_").replace("-", "_") or "GDELT"
        news_list.append({
            "news_id": _news_id("gdelt", title, link),
            "title": title,
            "body": f"Manchete coletada via GDELT DOC 2.0. Fonte original: {link}",
            "url": link,
            "published_at": None,
            "observed_at": observed_at,
            "source_timestamp": article["seendate"],
            "source_raw": article,
            "source": source,
            "related_tickers": _related_tickers(title),
            "is_synthetic": False,
        })
        if len(news_list) >= max_items:
            break
    return news_list


def fetch_google_news_rss(query: str, max_items: int = 6) -> list[dict[str, Any]]:
    """Fallback público: coleta manchetes via RSS e preserva o horário de publicação."""
    params = {"q": f"{query} when:1d", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
    url = f"{GOOGLE_NEWS_RSS_URL}?{urllib.parse.urlencode(params)}"
    headers = {**DEFAULT_HEADERS, "Accept": "application/rss+xml, application/xml;q=0.9,*/*;q=0.8"}
    req = urllib.request.Request(url, headers=headers)
    news_list: list[dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.fromstring(resp.read())
            items = tree.findall(".//item")[:max_items]
            for item in items:
                title_elem = item.find("title")
                title = html.unescape(title_elem.text.strip()) if title_elem is not None and title_elem.text else ""
                source_elem = item.find("source")
                source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Google_News"
                link_elem = item.find("link")
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                pub_date_elem = item.find("pubDate")
                if not title or not link or pub_date_elem is None or not pub_date_elem.text:
                    continue
                try:
                    published = parsedate_to_datetime(pub_date_elem.text)
                    if published.tzinfo is None:
                        raise ValueError("Manchete sem data com fuso")
                    published_at = published.astimezone(UTC).isoformat()
                except (TypeError, ValueError):
                    continue
                news_list.append({
                    "news_id": _news_id("rss", title, link),
                    "title": title,
                    "body": f"Manchete coletada via Google News RSS. Fonte original: {link}",
                    "url": link,
                    "published_at": published_at,
                    "source": source.replace(" ", "_"),
                    "related_tickers": _related_tickers(title),
                    "is_synthetic": False,
                })
    except (OSError, ET.ParseError):
        return []
    return news_list


def fetch_real_market_news(
    query: str = "Ibovespa B3",
    max_items: int = 6,
    timespan: str = "24h",
) -> list[dict[str, Any]]:
    """Busca notícias pela GDELT e usa Google News RSS somente como contingência."""
    gdelt_news = fetch_gdelt_market_news(query, max_items=max_items, timespan=timespan)
    if gdelt_news:
        return gdelt_news
    rss_query = re.sub(r"\s*(?:sourcelang|sourcecountry):\S+", "", query).strip()
    return fetch_google_news_rss(rss_query, max_items=max_items)


def build_live_market_package(output_dir: str | Path, timeframe: str = "1d", tickers: list[str] | None = None) -> Path:
    """Monta snapshot diário com preços coletados e carteira explicitamente simulada."""
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"{target} já existe. Escolha uma nova pasta para preservar os dados anteriores.")
    if timeframe != "1d":
        raise ValueError("A coleta suporta apenas 1d; períodos semanais/mensais não estão implementados.")
    stocks = tickers if tickers is not None else ["PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "WEGE3.SA"]
    if not stocks or len(set(stocks)) != len(stocks):
        raise ValueError("Selecione ao menos um ativo, sem duplicatas.")

    # Coletar e validar os dados obrigatórios antes de criar qualquer pacote.
    usd = fetch_awesomeapi_usd_brl()
    ibov = fetch_yahoo_chart("^BVSP")
    quotes = [fetch_yahoo_chart(ticker) for ticker in stocks]
    ref_date, previous_session = ibov["reference_date"], ibov["previous_session"]
    if any(q["reference_date"] != ref_date or q["previous_session"] != previous_session for q in quotes):
        raise RuntimeError("As cotações correspondem a sessões diferentes; coleta interrompida.")
    if usd["reference_date"] != ref_date:
        raise RuntimeError("Câmbio e bolsa correspondem a datas diferentes; coleta interrompida.")
    now = datetime.now(UTC)
    observed_times = [datetime.fromisoformat(q["observed_at"]) for q in [ibov, usd, *quotes]]
    if any(t > now or (now - t).total_seconds() > 7 * 86400 for t in observed_times):
        raise RuntimeError("Cotação com timestamp futuro ou mais de sete dias de atraso; coleta interrompida.")
    notes = [
        "Cotações públicas nos horários de cada fonte; podem ter atraso e não representam necessariamente o fechamento oficial.",
        "CARTEIRA SIMULADA: pesos iguais gerados para fins didáticos; preços sem ajuste de proventos/splits.",
        "O câmbio usa bid e varBid da AwesomeAPI; sua referência pode diferir do fechamento da bolsa.",
        "Notícias da janela recente até a coleta; podem ser posteriores à sessão das cotações.",
    ]
    news = fetch_real_market_news(build_market_news_query(stocks), max_items=6, timespan="24h")
    if not news:
        notes.append("Nenhuma manchete coletada. Ausência de resultado não significa ausência de notícias.")
    try:
        taxas = fetch_brasilapi_taxas()
    except RuntimeError as exc:
        taxas = {}
        notes.append(str(exc))
    if taxas:
        news.append({
            "news_id": "brasilapi_taxas", "title": f"Taxas consultadas: Selic em {taxas['SELIC']}% e CDI em {taxas['CDI']}% ao ano",
            "body": "Retrato das taxas na consulta, sem data de vigência informada neste endpoint; não é manchete jornalística.",
            "published_at": datetime.now(UTC).isoformat(), "source": "BrasilAPI_Consulta",
            "url": "https://brasilapi.com.br/api/taxas/v1", "related_tickers": [], "is_synthetic": False,
        })
    cutoff = datetime.now(UTC).isoformat()
    sectors = {"PETR4": "Petróleo e Gás", "VALE3": "Materiais Básicos", "ITUB4": "Financeiro", "BBDC4": "Financeiro", "BBAS3": "Financeiro", "WEGE3": "Bens Industriais"}
    weights = [round(1 / len(quotes), 8)] * len(quotes)
    weights[0] = 1 - sum(weights[1:])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".coleta-") as staging:
        stage = Path(staging) / "package"
        stage.mkdir()
        with (stage / "quotes.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ticker", "instrument_type", "currency", "previous_price", "current_price", "observed_at", "source", "adjustment_criteria", "is_synthetic"])
            for quote in [ibov, usd, *quotes]:
                ticker = quote["ticker"]
                kind = "index" if ticker == "IBOV" else "currency" if ticker == "USD/BRL" else "equity"
                currency = "POINTS" if kind == "index" else "BRL_PER_USD" if kind == "currency" else quote["currency"]
                source = "AWESOMEAPI" if kind == "currency" else "YAHOO_FINANCE"
                writer.writerow([ticker, kind, currency, quote["previous_price"], quote["current_price"], quote["observed_at"], source, "SEM_AJUSTE", "False"])
        with (stage / "positions.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ticker", "sector", "weight_start", "reference_date", "is_synthetic"])
            for quote, weight in zip(quotes, weights, strict=True):
                ticker = quote["ticker"]
                writer.writerow([ticker, sectors.get(ticker, "Geral"), weight, ref_date, "True"])
        (stage / "news.jsonl").write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in news), encoding="utf-8")
        (stage / "sources.json").write_text(json.dumps({"collected_at": cutoff, "quotes": [ibov, usd, *quotes], "taxas": taxas, "notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {
            "scenario_id": target.name, "reference_date": ref_date, "previous_session": previous_session,
            "cutoff_time": cutoff, "timezone": "America/Sao_Paulo", "is_synthetic": True,
            "data_notice": " ".join(notes),
            "files": [{"filename": name, "path": name, "sha256": compute_sha256(stage / name)} for name in ("quotes.csv", "positions.csv", "news.jsonl", "sources.json")],
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"{target} já existe; dados preservados.")
        stage.rename(target)
    return target
