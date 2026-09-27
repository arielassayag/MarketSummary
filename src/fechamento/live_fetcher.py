"""Coleta pública, sujeita a atraso e indisponibilidade, sem substituir fatos ausentes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import urllib.parse
import urllib.request
import warnings
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


def fetch_real_market_news(query: str = "Ibovespa B3", max_items: int = 4) -> list[dict[str, Any]]:
    """Lê manchetes RSS, preservando pubDate e link (que pode ser um redirecionamento)."""
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": f"{query} when:1d", "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419",
    })
    try:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            tree = ET.fromstring(resp.read())
        news = []
        for item in tree.findall(".//item"):
            try:
                title = item.findtext("title")
                link = item.findtext("link")
                published = parsedate_to_datetime(item.findtext("pubDate") or "")
                if not title or not link or published.tzinfo is None:
                    raise ValueError("Manchete sem título, link ou data com fuso")
                source = item.findtext("source") or "Google News RSS"
                related = [tk for tk in ["PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "WEGE3", "IBOV", "USD/BRL"] if tk in title.upper()]
                news.append({
                    "news_id": "rss_" + hashlib.sha256(link.encode()).hexdigest()[:12],
                    "title": title, "body": f"Manchete coletada de {source}: {title}",
                    "url": link, "published_at": published.astimezone(UTC).isoformat(),
                    "source": source, "related_tickers": related, "is_synthetic": False,
                })
                if len(news) >= max_items:
                    break
            except (ValueError, TypeError) as exc:
                warnings.warn(f"Manchete ignorada: {exc}", stacklevel=2)
        return news
    except Exception as exc:
        warnings.warn(f"Google News RSS indisponível; nenhuma manchete substituta será criada: {exc}", stacklevel=2)
        return []


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
    news = fetch_real_market_news()
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
