"""Módulo de ingestão e validação estrita de dados sintéticos de mercado.

Lê arquivos CSV e JSONL, valida hashes contra o manifesto, aplica contratos Pydantic
e separa estritamente erros bloqueantes, alertas revisáveis e exclusões documentadas.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .contracts import (
    InstrumentType,
    Manifest,
    NewsItem,
    Position,
    Quote,
)


@dataclass
class IngestionResult:
    manifest: Manifest | None = None
    quotes: dict[str, Quote] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)
    eligible_news: list[NewsItem] = field(default_factory=list)
    excluded_news: list[tuple[NewsItem, str]] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return len(self.blocking_errors) > 0


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_and_validate_package(package_dir: str | Path) -> IngestionResult:
    """Carrega e valida o pacote de dados do cenário a partir do diretório fornecido."""
    pdir = Path(package_dir)
    result = IngestionResult()

    manifest_path = pdir / "manifest.json"
    if not manifest_path.exists():
        result.blocking_errors.append(f"Arquivo de manifesto não encontrado em {manifest_path}")
        return result

    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest_raw = json.load(f)
        manifest = Manifest.model_validate(manifest_raw)
        result.manifest = manifest
    except Exception as e:
        result.blocking_errors.append(f"Erro ao validar manifest.json: {e}")
        return result

    # 1. Validação de integridade de hashes declarados no manifesto
    for file_entry in manifest.files:
        target_file = pdir / file_entry.path
        if not target_file.exists():
            result.blocking_errors.append(f"Arquivo declarado no manifesto não encontrado: {file_entry.path}")
            continue
        actual_hash = compute_sha256(target_file)
        if actual_hash != file_entry.sha256:
            result.blocking_errors.append(
                f"Hash SHA-256 divergente para {file_entry.path}: esperado {file_entry.sha256}, obtido {actual_hash}"
            )

    if result.is_blocked:
        return result

    # 2. Ingestão e validação de Cotações (quotes.csv)
    quotes_path = pdir / "quotes.csv"
    if not quotes_path.exists():
        result.blocking_errors.append(f"Arquivo quotes.csv não encontrado em {pdir}")
        return result

    try:
        with open(quotes_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                ticker = row.get("ticker", "").strip()
                if not ticker:
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: ticker ausente.")
                    continue

                if ticker in result.quotes:
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: ticker duplicado conflitante '{ticker}'.")
                    continue

                try:
                    prev_p = float(row.get("previous_price", 0))
                    curr_p = float(row.get("current_price", 0))
                except (ValueError, TypeError):
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: preços não numéricos para '{ticker}'.")
                    continue

                if prev_p <= 0 or curr_p <= 0:
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: preço menor ou igual a zero para '{ticker}'.")
                    continue

                try:
                    obs_at = datetime.fromisoformat(row.get("observed_at", ""))
                except Exception as e:
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: timestamp inválido para '{ticker}': {e}")
                    continue

                try:
                    quote = Quote(
                        ticker=ticker,
                        instrument_type=InstrumentType(row.get("instrument_type", "").lower()),
                        currency=row.get("currency", "").strip(),
                        previous_price=prev_p,
                        current_price=curr_p,
                        observed_at=obs_at,
                        source=row.get("source", "").strip(),
                        adjustment_criteria=row.get("adjustment_criteria", "").strip(),
                        is_synthetic=row.get("is_synthetic", "True").lower() in ("true", "1"),
                    )
                    result.quotes[ticker] = quote

                    # Alerta para oscilação atípica (>15%)
                    ret = (curr_p / prev_p) - 1.0
                    if abs(ret) > 0.15:
                        result.alerts.append(f"Oscilação atípica detectada em '{ticker}': {ret * 100:+.2f}%.")

                except Exception as e:
                    result.blocking_errors.append(f"quotes.csv linha {row_idx}: erro de validação em '{ticker}': {e}")

    except Exception as e:
        result.blocking_errors.append(f"Erro ao ler quotes.csv: {e}")

    # Verificar presença dos instrumentos macro essenciais
    if "IBOV" not in result.quotes:
        result.blocking_errors.append("Cotação obrigatória de benchmark 'IBOV' ausente em quotes.csv.")
    if "USD/BRL" not in result.quotes:
        result.blocking_errors.append("Cotação obrigatória de câmbio 'USD/BRL' ausente em quotes.csv.")

    # 3. Ingestão e validação de Posições da Carteira (positions.csv)
    positions_path = pdir / "positions.csv"
    if not positions_path.exists():
        result.blocking_errors.append(f"Arquivo positions.csv não encontrado em {pdir}")
        return result

    try:
        with open(positions_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            total_weight = 0.0
            for row_idx, row in enumerate(reader, start=2):
                ticker = row.get("ticker", "").strip()
                if not ticker:
                    result.blocking_errors.append(f"positions.csv linha {row_idx}: ticker ausente.")
                    continue

                if ticker in result.positions:
                    result.blocking_errors.append(f"positions.csv linha {row_idx}: posição duplicada para '{ticker}'.")
                    continue

                try:
                    weight = float(row.get("weight_start", 0))
                except (ValueError, TypeError):
                    result.blocking_errors.append(f"positions.csv linha {row_idx}: peso inválido para '{ticker}'.")
                    continue

                if weight < 0.0 or weight > 1.0:
                    result.blocking_errors.append(f"positions.csv linha {row_idx}: peso fora do intervalo [0, 1] ({weight}) para '{ticker}'.")
                    continue

                try:
                    ref_d = datetime.fromisoformat(row.get("reference_date", "")).date()
                except Exception:
                    try:
                        ref_d = datetime.strptime(row.get("reference_date", ""), "%Y-%m-%d").date()
                    except Exception as e:
                        result.blocking_errors.append(f"positions.csv linha {row_idx}: data inválida para '{ticker}': {e}")
                        continue

                try:
                    pos = Position(
                        ticker=ticker,
                        sector=row.get("sector", "").strip(),
                        weight_start=weight,
                        reference_date=ref_d,
                        is_synthetic=row.get("is_synthetic", "True").lower() in ("true", "1"),
                    )
                    result.positions[ticker] = pos
                    total_weight += weight
                except Exception as e:
                    result.blocking_errors.append(f"positions.csv linha {row_idx}: erro em '{ticker}': {e}")

            # Reconciliação dos pesos: soma deve ser 1.0 (tolerância de 1e-4)
            # Não renormalizar silenciosamente!
            if abs(total_weight - 1.0) > 1e-4:
                result.blocking_errors.append(
                    f"A soma dos pesos da carteira é {total_weight:.4f} (esperado 1.0000). Não é permitida renormalização silenciosa."
                )

    except Exception as e:
        result.blocking_errors.append(f"Erro ao ler positions.csv: {e}")

    # Checar se todos os tickers da carteira possuem cotação em quotes
    for pos_ticker in result.positions:
        if pos_ticker not in result.quotes:
            result.blocking_errors.append(
                f"Ativo da carteira '{pos_ticker}' não possui cotação correspondente em quotes.csv."
            )

    # 4. Ingestão e validação de Notícias (news.jsonl)
    news_path = pdir / "news.jsonl"
    if not news_path.exists():
        result.blocking_errors.append(f"Arquivo news.jsonl não encontrado em {pdir}")
        return result

    try:
        with open(news_path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item_raw = json.loads(line)
                    news_item = NewsItem.model_validate(item_raw)

                    # Verificar horário de corte (Cutoff Time)
                    if manifest and news_item.published_at > manifest.cutoff_time:
                        result.excluded_news.append((
                            news_item,
                            f"Publicada em {news_item.published_at.isoformat()}, posterior ao horário de corte {manifest.cutoff_time.isoformat()}"
                        ))
                    else:
                        result.eligible_news.append(news_item)

                except Exception as e:
                    result.alerts.append(f"news.jsonl linha {line_idx}: notícia inválida ignorada ({e})")

    except Exception as e:
        result.blocking_errors.append(f"Erro ao ler news.jsonl: {e}")

    return result
