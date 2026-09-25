"""Catálogo de modelos do OpenRouter: consulta, validação e seleção.

O snapshot público (GET /models) é salvo em data/raw com a data da consulta e a
seleção é gravada em configs/models.lock.yaml. IDs não são fixados por
conhecimento antigo: o lock valida contra o catálogo da execução.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

CATALOG_URL = "https://openrouter.ai/api/v1/models"


@dataclass
class CatalogEntry:
    id: str
    name: str
    context_length: int
    input_price_usd_per_m: float
    output_price_usd_per_m: float
    supported_parameters: list[str]

    def supports(self, parameter: str) -> bool:
        return parameter in self.supported_parameters


def fetch_catalog(out_path: Path, timeout_s: int = 60) -> int:
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "market-close-eval/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - URL fixa e HTTPS
        data = json.loads(resp.read().decode("utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return len(data.get("data", []))


def _price(raw: str | float | None) -> float:
    if raw is None:
        return float("nan")
    try:
        return float(raw) * 1_000_000.0  # OpenRouter devolve preço por token
    except (TypeError, ValueError):
        return float("nan")


def load_catalog(path: Path) -> dict[str, CatalogEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, CatalogEntry] = {}
    for raw in data.get("data", []):
        pricing = raw.get("pricing", {}) or {}
        entry = CatalogEntry(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            context_length=int(raw.get("context_length") or 0),
            input_price_usd_per_m=_price(pricing.get("prompt")),
            output_price_usd_per_m=_price(pricing.get("completion")),
            supported_parameters=[str(p) for p in (raw.get("supported_parameters") or [])],
        )
        if entry.id:
            entries[entry.id] = entry
    return entries


def validate_model_ids(
    catalog: dict[str, CatalogEntry], model_ids: list[str], require_structured_outputs: bool = True
) -> list[str]:
    """Retorna lista de erros (vazia = OK). Falha clara, sem substituição silenciosa."""
    errors: list[str] = []
    for mid in model_ids:
        entry = catalog.get(mid)
        if entry is None:
            errors.append(f"modelo inexistente no catálogo: {mid}")
            continue
        if require_structured_outputs and not entry.supports("structured_outputs"):
            errors.append(f"modelo sem suporte a structured_outputs: {mid}")
        if entry.context_length and entry.context_length < 16000:
            errors.append(f"contexto insuficiente para o pacote: {mid} ({entry.context_length})")
    return errors


def select_models(
    catalog: dict[str, CatalogEntry],
    preferences: dict[str, list[str]],
    judge_preferences: list[str],
    *,
    exclude_from_judge: set[str] | None = None,
) -> tuple[dict[str, str], str, list[str]]:
    """Seleciona o 1º ID disponível/capaz de cada slot. Retorna (slots, judge, warnings)."""
    warnings: list[str] = []
    selected: dict[str, str] = {}
    for slot, prefs in preferences.items():
        chosen: str | None = None
        for mid in prefs:
            errs = validate_model_ids(catalog, [mid])
            if not errs:
                chosen = mid
                break
            warnings.append(f"slot {slot}: {mid} indisponível ({errs[0]})")
        if chosen is None:
            raise RuntimeError(f"nenhum candidato do slot '{slot}' está disponível no catálogo")
        selected[slot] = chosen

    judge_id: str | None = None
    excluded = exclude_from_judge or set(selected.values())
    for mid in judge_preferences:
        errs = validate_model_ids(catalog, [mid])
        if errs:
            warnings.append(f"judge: {mid} indisponível ({errs[0]})")
            continue
        if mid in excluded:
            warnings.append(f"judge: {mid} está entre os candidatos; tentando próxima preferência")
            continue
        judge_id = mid
        break
    if judge_id is None:
        # fallback documentado: reutilizar um candidato como judge (limitação registrada)
        judge_id = next(iter(selected.values()))
        warnings.append(
            f"FALLBACK: judge reutilizando candidato '{judge_id}' (nenhum avaliador externo disponível); "
            "registre esta limitação no relatório"
        )
    return selected, judge_id, warnings


def write_lock(
    *,
    lock_path: Path,
    snapshot_path: Path,
    selected: dict[str, str],
    judge_id: str,
    catalog: dict[str, CatalogEntry],
    n_models: int,
) -> None:
    lines: list[str] = [
        "# Gerado por `lock-models` — não editar à mão sem revalidar contra o catálogo.",
        "catalog_snapshot:",
        f"  timestamp: \"{datetime.now(UTC).isoformat()}\"",
        f"  source: \"{CATALOG_URL}\"",
        f"  file: \"{snapshot_path.as_posix()}\"",
        f"  n_models: {n_models}",
        "",
        "models:",
    ]

    def entry_lines(mid: str, role: str, slot: str, rationale: str) -> list[str]:
        e = catalog[mid]
        return [
            f"  - friendly_name: \"{e.name}\"",
            f"    exact_model_id: \"{e.id}\"",
            f"    provider: \"{e.id.split('/', 1)[0]}\"",
            f"    role: {role}",
            f"    slot: {slot}",
            f"    input_price_usd_per_m: {e.input_price_usd_per_m:.4f}",
            f"    output_price_usd_per_m: {e.output_price_usd_per_m:.4f}",
            f"    context_length: {e.context_length}",
            f"    supported_parameters: {json.dumps(e.supported_parameters)}",
            f"    rationale: >-{rationale}",
        ]

    for slot, mid in selected.items():
        lines += entry_lines(mid, "candidate", slot, f"\n      Selecionado automaticamente no slot {slot} (1ª preferência disponível e capaz).")
    lines += entry_lines(judge_id, "judge", "judge", "\n      Avaliador forte fora do conjunto de candidatos, quando disponível.")
    lock_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
