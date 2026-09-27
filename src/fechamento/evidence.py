"""Módulo de construção do FactBook e organização de evidências para o comentário de fechamento.

O FactBook é a única fonte da verdade quantitativa do sistema. Cada fato possui um
identificador estável, valor numérico exato, valor formatado em pt-BR, unidade,
fórmula e rastreabilidade aos dados de entrada.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from .contracts import Fact, FactBook, Manifest, NewsItem, Unit
from .metrics import CalculatedMetrics


def format_brazilian_pct(value: float, decimal_places: int = 2, show_sign: bool = True) -> str:
    """Formata fração decimal como porcentagem no padrão brasileiro: ex: +1,25% ou -0,64%."""
    pct = value * 100.0
    sign = "+" if show_sign and pct > 0 else ""
    formatted = f"{sign}{pct:.{decimal_places}f}%"
    return formatted.replace(".", ",")


def format_brazilian_bps(value: float, decimal_places: int = 1, show_sign: bool = True) -> str:
    """Formata valor em pontos-base: ex: +59,7 bps ou -29,0 bps."""
    sign = "+" if show_sign and value > 0 else ""
    formatted = f"{sign}{value:.{decimal_places}f} bps"
    return formatted.replace(".", ",")


def format_brazilian_currency(value: float, decimal_places: int = 4) -> str:
    """Formata cotação cambial em padrão brasileiro: ex: 5,4150."""
    formatted = f"{value:.{decimal_places}f}"
    return formatted.replace(".", ",")


def compute_factbook_hash(factbook: FactBook) -> str:
    """Gera hash SHA-256 canônico do FactBook."""
    serialized = factbook.model_dump_json()
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_factbook(
    metrics: CalculatedMetrics,
    manifest: Manifest,
    eligible_news: list[NewsItem] | None = None,
) -> FactBook:
    """Constrói o FactBook estruturado com identificadores determinísticos."""
    facts: dict[str, Fact] = {}

    # 1. Fatos Macroeconômicos e de Mercado
    facts["ibov.return_pct"] = Fact(
        fact_id="ibov.return_pct",
        name="Retorno diário do IBOV (simulado)",
        value=metrics.ibov_return_pct,
        formatted_value=format_brazilian_pct(metrics.ibov_return_pct),
        unit=Unit.PCT,
        period="diario",
        formula="P_atual / P_anterior - 1",
        input_refs=["quotes.csv:IBOV"],
    )

    facts["usd_brl.change_pct"] = Fact(
        fact_id="usd_brl.change_pct",
        name="Variação diária do USD/BRL (reais por dólar)",
        value=metrics.usd_brl.change_pct,
        formatted_value=format_brazilian_pct(metrics.usd_brl.change_pct),
        unit=Unit.PCT,
        period="diario",
        formula="P_atual / P_anterior - 1",
        input_refs=["quotes.csv:USD/BRL"],
    )

    facts["usd_brl.level"] = Fact(
        fact_id="usd_brl.level",
        name="Cotação de fechamento USD/BRL",
        value=metrics.usd_brl.current_price,
        formatted_value=format_brazilian_currency(metrics.usd_brl.current_price),
        unit=Unit.BRL_PER_USD,
        period="diario",
        formula="Cotação de fechamento",
        input_refs=["quotes.csv:USD/BRL"],
    )

    # Extrai taxas oficiais se presentes nas notícias (BrasilAPI)
    if eligible_news:
        for n in eligible_news:
            combined = f"{n.title} {n.body}"
            if "Selic" in combined and "macro.selic.rate" not in facts:
                selic_m = re.search(r"Selic\s+(?:em|a)\s+([\d,\.]+)%", combined, re.IGNORECASE)
                if selic_m:
                    val_str = selic_m.group(1).replace(",", ".")
                    try:
                        v_fl = float(val_str) / 100.0
                        facts["macro.selic.rate"] = Fact(
                            fact_id="macro.selic.rate",
                            name="Taxa Selic oficial (ao ano)",
                            value=v_fl,
                            formatted_value=f"{float(val_str):.2f}%",
                            unit=Unit.PCT,
                            period="anual",
                            formula="Taxa Meta Selic Anual",
                            input_refs=[f"news:{n.news_id}"],
                        )
                    except Exception:
                        pass

            if "CDI" in combined and "macro.cdi.rate" not in facts:
                cdi_m = re.search(r"CDI\s+(?:em|a)\s+([\d,\.]+)%", combined, re.IGNORECASE)
                if cdi_m:
                    val_str = cdi_m.group(1).replace(",", ".")
                    try:
                        v_fl = float(val_str) / 100.0
                        facts["macro.cdi.rate"] = Fact(
                            fact_id="macro.cdi.rate",
                            name="Taxa CDI oficial (ao ano)",
                            value=v_fl,
                            formatted_value=f"{float(val_str):.2f}%",
                            unit=Unit.PCT,
                            period="anual",
                            formula="Taxa CDI Anual",
                            input_refs=[f"news:{n.news_id}"],
                        )
                    except Exception:
                        pass

    # 2. Fatos da Carteira Fictícia
    facts["portfolio.return_pct"] = Fact(
        fact_id="portfolio.return_pct",
        name="Retorno diário da carteira fictícia",
        value=metrics.portfolio_return_pct,
        formatted_value=format_brazilian_pct(metrics.portfolio_return_pct),
        unit=Unit.PCT,
        period="diario",
        formula="soma(peso_inicial_i * retorno_i)",
        input_refs=["positions.csv", "quotes.csv"],
    )

    facts["portfolio.spread_vs_ibov_bps"] = Fact(
        fact_id="portfolio.spread_vs_ibov_bps",
        name="Diferença da carteira vs IBOV em pontos-base",
        value=metrics.portfolio_vs_ibov_bps,
        formatted_value=format_brazilian_bps(metrics.portfolio_vs_ibov_bps),
        unit=Unit.BPS,
        period="diario",
        formula="(retorno_carteira - retorno_ibov) * 10.000",
        input_refs=["positions.csv", "quotes.csv"],
    )

    # 3. Fatos de Ativos Individuais
    for ticker, am in metrics.asset_metrics.items():
        ret_id = f"asset.{ticker}.return_pct"
        contrib_id = f"asset.{ticker}.contribution_bps"

        facts[ret_id] = Fact(
            fact_id=ret_id,
            name=f"Retorno diário de {ticker}",
            value=am.return_pct,
            formatted_value=format_brazilian_pct(am.return_pct),
            unit=Unit.PCT,
            period="diario",
            formula="P_atual / P_anterior - 1",
            input_refs=[f"quotes.csv:{ticker}"],
        )

        facts[contrib_id] = Fact(
            fact_id=contrib_id,
            name=f"Contribuição de {ticker} para a carteira",
            value=am.contribution_bps,
            formatted_value=format_brazilian_bps(am.contribution_bps),
            unit=Unit.BPS,
            period="diario",
            formula="peso_inicial * retorno * 10.000",
            input_refs=[f"positions.csv:{ticker}", f"quotes.csv:{ticker}"],
        )

    # 4. Fatos Setoriais
    for sector_name, sm in metrics.sector_metrics.items():
        nfkd = unicodedata.normalize("NFKD", sector_name)
        sec_ascii = "".join(c for c in nfkd if not unicodedata.combining(c)).replace(" ", "_")
        sec_fact_id = f"sector.{sec_ascii}.contribution_bps"

        sector_fact = Fact(
            fact_id=sec_fact_id,
            name=f"Contribuição do setor {sector_name}",
            value=sm.contribution_bps,
            formatted_value=format_brazilian_bps(sm.contribution_bps),
            unit=Unit.BPS,
            period="diario",
            formula="soma(contribuicoes_ativos_do_setor)",
            input_refs=[f"positions.csv:{t}" for t in sm.tickers],
        )
        facts[sec_fact_id] = sector_fact

        # Aliases para resiliência a variações de acentuação geradas pelo LLM
        alt_id_1 = f"sector.{sector_name.replace(' ', '_')}.contribution_bps"
        alt_id_2 = f"sector.{sector_name.replace(' ', '_').replace('ã', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o')}.contribution_bps"
        facts[alt_id_1] = sector_fact
        facts[alt_id_2] = sector_fact

    return FactBook(
        scenario_id=manifest.scenario_id,
        reference_date=manifest.reference_date,
        facts=facts,
        is_synthetic=manifest.is_synthetic,
        data_notice=manifest.data_notice,
    )


@dataclass(frozen=True)
class EvidencePackage:
    factbook: FactBook
    eligible_news: list[NewsItem]
    excluded_news: list[tuple[NewsItem, str]]
    news_by_ticker: dict[str, list[NewsItem]] = field(default_factory=dict)


def organize_evidence(
    metrics: CalculatedMetrics,
    manifest: Manifest,
    eligible_news: list[NewsItem],
    excluded_news: list[tuple[NewsItem, str]],
) -> EvidencePackage:
    """Organiza o FactBook e mapeia as notícias elegíveis aos tickers da carteira."""
    factbook = build_factbook(metrics, manifest, eligible_news)

    news_by_ticker: dict[str, list[NewsItem]] = {}
    for item in eligible_news:
        for ticker in item.related_tickers:
            news_by_ticker.setdefault(ticker, []).append(item)

    return EvidencePackage(
        factbook=factbook,
        eligible_news=eligible_news,
        excluded_news=excluded_news,
        news_by_ticker=news_by_ticker,
    )
