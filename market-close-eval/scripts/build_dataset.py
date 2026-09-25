"""Constrói o dataset congelado de 20 pregões da B3 (2025-01 a 2026-07).

- Fatos de índice: série diária ^BVSP (Yahoo Finance, agregador) em data/raw.
- Fatos de câmbio: PTAX (Banco Central, API Olinda) em data/raw.
- Fatos de eventos: paráfrases factuais curtas com URL das matérias verificadas
  durante a construção do dataset (ver scripts/case_specs.py).

O split dev/holdout é estratificado por regime com seed fixa (42) e os dois
casos showcase são marcados deterministicamente ANTES de qualquer execução de
modelo. Nenhuma resposta de modelo é usada nesta etapa.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from case_specs import BCB_PTAX_NAME, BCB_PTAX_URL, CASE_SPECS, YAHOO_NAME, YAHOO_URL, CaseSpec

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CASES = ROOT / "data" / "cases"
SPLIT_SEED = 42
SHOWCASE_SEED = 2026

DEV_PER_GROUP = {"calm": 3, "domestic_macro": 3, "global_macro": 3, "corporate": 3, "stress": 2}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ibovespa() -> dict[str, float]:
    rows = json.loads((RAW / "yahoo_bvsp_closes.json").read_text())
    return {d: float(c) for d, c in rows}


def load_ptax() -> dict[str, dict[str, object]]:
    data = json.loads((RAW / "bcb_ptax_usdbrl_2025-01-01_2026-07-31.json").read_text())
    per_day: dict[str, dict[str, object]] = {}
    for row in data["value"]:
        day = str(row["dataHoraCotacao"])[:10]
        # mantém a última cotação do dia (PTAX de fechamento)
        if day not in per_day or str(row["dataHoraCotacao"]) > str(per_day[day]["ts"]):
            per_day[day] = {"ts": str(row["dataHoraCotacao"]), "venda": float(row["cotacaoVenda"])}
    return per_day


def to_iso_brt(ts: str) -> str:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
    return dt.replace(tzinfo=timezone(timedelta(hours=-3))).isoformat()


def format_pct(value: float) -> str:
    return f"{value:+.2f}".replace(".", ",")


def source_block(name: str, url: str, tier: int, published_at: str | None) -> dict[str, object]:
    return {"name": name, "url": url, "source_tier": tier, "published_at": published_at}


def base_facts(
    date: str, ibov: dict[str, float], ptax: dict[str, dict[str, object]]
) -> tuple[list[dict[str, object]], float, str]:
    close = ibov[date]
    prev_dates = sorted(d for d in ibov if d < date)
    prev_date = prev_dates[-1]
    prev_close = ibov[prev_date]
    ret = round((close / prev_close - 1) * 100, 2)
    direction = "up" if ret > 0 else ("down" if ret < 0 else "flat")
    obs = f"{date}T18:00:00-03:00"
    close_br = f"{close:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")

    facts: list[dict[str, object]] = [
        {
            "fact_id": "IDX-01",
            "category": "index",
            "subject": "Ibovespa",
            "statement": f"O Ibovespa fechou aos {close_br} pontos em {date} (série ^BVSP do agregador; validar contra a B3).",
            "measure_kind": "level",
            "value": close,
            "unit": "points",
            "direction": "na",
            "observed_at": obs,
            "source": source_block(YAHOO_NAME, YAHOO_URL, 3, date),
        },
        {
            "fact_id": "IDX-02",
            "category": "index",
            "subject": "Ibovespa",
            "statement": (
                f"O Ibovespa variou {format_pct(ret)}% em {date} em relação ao "
                f"fechamento anterior ({prev_date})."
            ),
            "measure_kind": "return_pct",
            "value": ret,
            "unit": "pct",
            "direction": direction,
            "observed_at": obs,
            "source": source_block(YAHOO_NAME, YAHOO_URL, 3, date),
        },
    ]

    if date in ptax:
        cur = ptax[date]
        prev_ptax_dates = sorted(d for d in ptax if d < date)
        prev_p = ptax[prev_ptax_dates[-1]]
        chg = round((float(cur["venda"]) / float(prev_p["venda"]) - 1) * 100, 2)
        fx_dir = "up" if chg > 0 else ("down" if chg < 0 else "flat")
        ts_iso = to_iso_brt(str(cur["ts"]))
        facts += [
            {
                "fact_id": "FX-01",
                "category": "currency",
                "subject": "USD/BRL (PTAX fechamento)",
                "statement": f"A PTAX de fechamento em {date} foi de R$ {float(cur['venda']):.4f} por US$ (cotação de venda).",
                "measure_kind": "level",
                "value": float(cur["venda"]),
                "unit": "brl_per_usd",
                "direction": "na",
                "observed_at": ts_iso,
                "source": source_block(BCB_PTAX_NAME, BCB_PTAX_URL, 1, date),
            },
            {
                "fact_id": "FX-02",
                "category": "currency",
                "subject": "USD/BRL (PTAX fechamento)",
                "statement": (
                    f"A PTAX de fechamento variou {format_pct(chg)}% em {date} em "
                    f"relação ao dia anterior ({prev_ptax_dates[-1]})."
                ),
                "measure_kind": "change_pct",
                "value": chg,
                "unit": "pct",
                "direction": fx_dir,
                "observed_at": ts_iso,
                "source": source_block(BCB_PTAX_NAME, BCB_PTAX_URL, 1, date),
            },
        ]
    else:
        raise RuntimeError(f"PTAX ausente para {date}")

    return facts, ret, direction


def build_case(spec: CaseSpec, split: str, ibov: dict[str, float], ptax: dict[str, dict[str, object]]) -> dict[str, object]:
    facts, ret, direction = base_facts(spec.date, ibov, ptax)
    for ev in spec.events:
        facts.append(
            {
                "fact_id": ev.fact_id,
                "category": ev.category,
                "subject": ev.subject,
                "statement": ev.statement,
                "measure_kind": ev.measure_kind,
                "value": ev.value,
                "unit": ev.unit,
                "direction": ev.direction,
                "observed_at": f"{spec.date}T19:00:00-03:00",
                "source": source_block(ev.source_name, ev.url, ev.tier, ev.published_at),
            }
        )

    event_ids = [ev.fact_id for ev in spec.events]
    importance: dict[str, int] = {"IDX-02": 5, "FX-01": 4, "FX-02": 4, "IDX-01": 3}
    for i, eid in enumerate(event_ids):
        importance[eid] = 5 if i == 0 else 2

    main_news = event_ids[:2] if event_ids else []
    case: dict[str, object] = {
        "case_id": f"{spec.date}_{spec.slug}",
        "date": spec.date,
        "split": split,
        "regime": spec.regime,
        "showcase": False,
        "input": {"facts": facts},
        "reference": {
            "critical_fact_ids": ["IDX-02", "FX-02"],
            "must_mention_fact_ids": ["IDX-02", "FX-01"] + main_news,
            "useful_fact_ids": ["IDX-01"] + event_ids[2:],
            "fact_importance": importance,
            "accepted_driver_groups": [
                {"label": label, "evidence_ids": ids, "confidence": conf} for label, ids, conf in spec.drivers
            ],
            "forbidden_conclusions": [
                {"description": d, "severity": sev} for d, sev in spec.forbidden
            ],
            "judge_notes": (spec.notes + " " + LIMITATIONS_TEXT).strip(),
        },
        "review": {
            "status": "draft",
            "reviewer": None,
            "reviewed_at": None,
            "notes": "Caso gerado automaticamente a partir de fontes verificadas; requer revisão humana antes de publicação.",
        },
    }
    return case


LIMITATIONS_TEXT = (
    "Limitações registradas: (1) fechamento do Ibovespa obtido de agregador "
    "(série ^BVSP do Yahoo Finance); validar contra a B3 antes de publicar; "
    "(2) PTAX é taxa de referência do BCB (~13h/fechamento) e pode diferir do "
    "fechamento do dólar à vista citado pela imprensa; (3) sem dados de curva "
    "de juros em pontos-base e sem contribuições em bps por ação neste dataset."
)


def main() -> None:
    ibov = load_ibovespa()
    ptax = load_ptax()

    # split estratificado por regime, seed fixa
    rng = random.Random(SPLIT_SEED)
    groups: dict[str, list[CaseSpec]] = {}
    for spec in CASE_SPECS:
        groups.setdefault(spec.regime, []).append(spec)

    assignments: dict[str, str] = {}
    for regime, specs in sorted(groups.items()):
        specs = sorted(specs, key=lambda s: s.date)
        rng.shuffle(specs)
        n_holdout = len(specs) - DEV_PER_GROUP[regime]
        for i, spec in enumerate(specs):
            assignments[spec.date] = "holdout" if i < n_holdout else "dev"

    # showcase: primeiro caso dev de cada grupo-alvo na ordem já embaralhada (determinístico, antes de qualquer execução)
    rng_show = random.Random(SHOWCASE_SEED)
    showcase_dates: set[str] = set()
    for regime in ("domestic_macro", "calm"):
        devs = sorted([s.date for s in groups[regime] if assignments[s.date] == "dev"])
        rng_show.shuffle(devs)
        showcase_dates.add(devs[0])

    written: list[dict[str, object]] = []
    queue_rows: list[dict[str, object]] = []
    for spec in CASE_SPECS:
        split = assignments[spec.date]
        case = build_case(spec, split, ibov, ptax)
        if spec.date in showcase_dates:
            case["showcase"] = True
        out_dir = CASES / split
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{case['case_id']}.json"
        payload = json.dumps(case, ensure_ascii=False, indent=2)
        out_path.write_text(payload, encoding="utf-8")
        written.append(
            {
                "case_id": case["case_id"],
                "date": spec.date,
                "split": split,
                "regime": spec.regime,
                "showcase": case["showcase"],
                "path": str(out_path.relative_to(ROOT)),
                "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                "n_facts": len(case["input"]["facts"]),
            }
        )
        for f in case["input"]["facts"]:
            src = f["source"]
            queue_rows.append(
                {
                    "case_id": case["case_id"],
                    "date": spec.date,
                    "split": split,
                    "regime": spec.regime,
                    "fact_id": f["fact_id"],
                    "category": f["category"],
                    "subject": f["subject"],
                    "measure_kind": f["measure_kind"],
                    "value": f["value"],
                    "unit": f["unit"],
                    "direction": f["direction"],
                    "source_name": src["name"],
                    "source_url": src["url"],
                    "source_tier": src["source_tier"],
                    "statement": f["statement"],
                    "needs_human_validation": "true",
                    "notes": "",
                }
            )

    queue_path = ROOT / "data" / "human_review_queue.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(queue_rows[0].keys()))
        writer.writeheader()
        writer.writerows(queue_rows)

    raw_files = sorted(RAW.glob("*.json"))
    manifest = {
        "generated_at": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
        "method": (
            "20 pregões da B3 (2025-01-02 a 2026-07-31) selecionados por amplitude de retorno "
            "do Ibovespa e estratificados em 5 regimes (4 casos cada). Datas verificadas por "
            "busca em fontes de imprensa (Tier 3) e notas oficiais (Tier 1, BCB) em 2026-08-27. "
            "Split dev/holdout estratificado com seed 42 antes de qualquer execução de modelo. "
            "Showcases marcados deterministicamente (seed 2026) antes de qualquer execução."
        ),
        "split_seed": SPLIT_SEED,
        "showcase_seed": SHOWCASE_SEED,
        "dev_cases": sum(1 for w in written if w["split"] == "dev"),
        "holdout_cases": sum(1 for w in written if w["split"] == "holdout"),
        "limitations": [
            "Fechamentos do Ibovespa vindos de agregador (Yahoo ^BVSP); fonte oficial B3 pendente de validação humana.",
            "PTAX (~13h/fechamento BCB) difere do dólar à vista de imprensa; casos citam ambas as referências quando disponíveis.",
            "Sem dados de curva de juros em pontos-base e sem contribuições em bps por ação; fatos contribution_bps não existem no dataset.",
            "Fatos de eventos são paráfrases curtas de matérias Tier 3; nenhum trecho extensão reproduzido.",
            "Todos os casos estão em review.status=draft; publicação exige revisão humana completa (ver data/human_review_queue.csv).",
        ],
        "raw_sources": [
            {"path": str(p.relative_to(ROOT)), "sha256": sha256_file(p)} for p in raw_files
        ],
        "cases": written,
    }
    (ROOT / "data" / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_dev = sum(1 for w in written if w["split"] == "dev")
    print(f"casos escritos: {len(written)} (dev={n_dev}, holdout={len(written) - n_dev})")
    print(f"showcases: {sorted(showcase_dates)}")
    print(f"fila de revisão: {queue_path} ({len(queue_rows)} fatos)")


if __name__ == "__main__":
    main()
