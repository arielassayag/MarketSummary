"""Diagnóstico imutável do risco efetivo: base macro, evento e corte arquivados.

O SHA dos bytes entra no DailyRecord; um selo preparatório autentica o append e um evento
posterior vincula registro e anexo, sem ciclo de hash. Registros sem esse marcador conservam
o contrato anterior.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import FundConfig
from ..hashing import sha256_file, sha256_obj, sha256_text
from ..risk.analytics import risk_decomposition
from ..risk.event_scaling import apply_event_windows
from ..risk.idio import kappa_f
from ..risk.types import RiskModel
from .track_record import (
    CSV_COLUMNS,
    GENESIS_RECORD_HASH,
    _cell,
    record_consistency,
    record_summary,
    write_exclusive,
)

MARKER = "risco_diario_v1"
POLICY = "cdp.risco_diario.base_macro_evento/v1"
FOLDER = "risco_diario"
EVENT = "DAILY_RISK_BASIS"
PREPARED_EVENT = "DAILY_RISK_PREPARED"


def text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def frame(value: pd.DataFrame) -> dict:
    return {
        "index": [str(x) for x in value.index],
        "columns": list(map(str, value.columns)),
        "index_name": value.index.name,
        "columns_name": value.columns.name,
        "values": [
            [float(x) if pd.notna(x) and math.isfinite(float(x)) else None for x in row]
            for row in value.to_numpy()
        ],
    }


def unframe(value: dict, *, dates: bool = False) -> pd.DataFrame:
    idx = pd.to_datetime(value["index"]) if dates else value["index"]
    out = pd.DataFrame(value["values"], index=idx, columns=value["columns"], dtype=float)
    out.index.name = value["index_name"]
    out.columns.name = value["columns_name"]
    return out


def model_data(model: RiskModel | None) -> dict | None:
    if model is None:
        return None
    data = {
        "as_of": str(model.as_of),
        "B": frame(model.exposures),
        "F": frame(model.factor_cov),
        "D": frame(model.specific_var.to_frame("D")),
        "factor_returns": frame(model.factor_returns),
        "groups": model.factor_groups,
        "meta": model.meta,
    }
    # Hashes integrais dos bytes JSON, sem arredondamento do hash semântico legado.
    data["matrix_hashes"] = {n: sha256_text(text(data[n])) for n in ("B", "F", "D")}
    return data


def restore(data: dict) -> RiskModel:
    return RiskModel(
        as_of=date.fromisoformat(data["as_of"]),
        exposures=unframe(data["B"]),
        factor_cov=unframe(data["F"]),
        specific_var=unframe(data["D"])["D"],
        factor_returns=unframe(data["factor_returns"], dates=True),
        specific_returns=pd.DataFrame(),
        factor_groups=data["groups"],
        meta=data["meta"],
    )


def market_data(md) -> dict:
    names = (
        "close",
        "adj_close",
        "volume",
        "fx",
        "fundamentals",
        "short_interest",
        "lending",
        "benchmarks",
        "rates",
    )
    return {
        "manifest": md.manifest.model_dump(mode="json"),
        "manifest_sha256": sha256_text(text(md.manifest.model_dump(mode="json"))),
        "tables_sha256": {
            n: sha256_text(
                getattr(md, n).to_json(orient="split", date_format="iso", double_precision=15)
            )
            for n in names
        },
        "universe_sha256": {
            n: sha256_text(
                getattr(md.universe, n).to_json(
                    orient="split", date_format="iso", double_precision=15
                )
            )
            for n in ("issuers", "lines")
        },
        "non_pit_sources": [
            s.model_dump(mode="json") for s in md.manifest.sources if not s.point_in_time
        ],
    }


def measures(model: RiskModel | None, w: pd.Series, required: list[str], kappa: float) -> dict:
    missing = sorted(set(required) - set(model.factor_names if model else []))
    outside = sorted(set(w[w != 0].index) - set(model.assets if model else []))
    valid = model is not None and not missing and not outside
    reason = []
    if model is None:
        reason.append("modelo ausente")
    if missing:
        reason.append("macro requerido ausente")
    if outside:
        reason.append("posição fora do modelo")
    values = {
        "vol": None,
        "vol_kf": None,
        "factor_vol": None,
        "specific_vol": None,
        "idio": None,
        "idio_kf": None,
    }
    if valid:
        try:
            held = w[w != 0].index
            if (
                not np.isfinite(model.exposures.loc[held].to_numpy()).all()
                or not np.isfinite(model.factor_cov.to_numpy()).all()
                or not np.isfinite(model.specific_var.loc[held].to_numpy()).all()
            ):
                raise ValueError("B/F/D não finitos")
            d = risk_decomposition(w, model)
            fv, sv = d.factor_vol**2, d.specific_vol**2
            values = {
                "vol": d.total_vol,
                "vol_kf": math.sqrt(kappa * fv + sv),
                "factor_vol": d.factor_vol,
                "specific_vol": d.specific_vol,
                "idio": sv / (fv + sv) if fv + sv else None,
                "idio_kf": sv / (kappa * fv + sv) if kappa * fv + sv else None,
            }
        except (ValueError, KeyError, np.linalg.LinAlgError):
            valid = False
            reason.append("B/F/D inválidos para a posição")
    return {
        "complete": valid,
        "reasons": reason,
        "missing_macro": missing,
        "outside_model": outside,
        **values,
    }


def build(
    ctx, cfg: FundConfig, positions, nav: float, model_prev, md_prev=None, *, previous_sources=None
) -> dict:
    from ..portfolio.optimizer import metodologia_ativa

    w = pd.Series(dtype=float)
    for p in positions:
        if p.market_value_usd:
            w.loc[p.issuer_id] = w.get(p.issuer_id, 0.0) + p.market_value_usd / nav
    w = w[w != 0].sort_index()
    required = ["macro:" + s for s in cfg.risk_model.macro_factors]
    k, info = (
        kappa_f(ctx.model, cfg)
        if ctx.model is not None and metodologia_ativa(cfg)
        else (1.0, {"mode": "legado"})
    )
    ms = {
        "base": measures(ctx.model, w, required, k),
        "evento": measures(ctx.risk_model, w, required, k),
    }
    binding = (
        min(ms, key=lambda n: ms[n]["idio_kf"])
        if all(v["complete"] and v["idio_kf"] is not None for v in ms.values())
        else None
    )
    config = cfg.model_dump(mode="json")
    return {
        "policy": POLICY,
        "session": str(ctx.date),
        "cutoffs": {
            "base_as_of": str(ctx.model.as_of) if ctx.model is not None else None,
            "previous_base_as_of": str(model_prev.as_of) if model_prev is not None else None,
            "event_session": str(ctx.date),
            "returns_through": str(ctx.date),
        },
        "nav_usd": nav,
        "weights": w.to_dict(),
        "config": config,
        "config_hash": cfg.config_hash(),
        "config_bytes_sha256": sha256_text(text(config)),
        "required_macro": required,
        "kappa_f": k,
        "kappa_info": info,
        "countries": ctx.panel.assets["country"].to_dict(),
        "models": {
            "base": model_data(ctx.model),
            "evento": model_data(ctx.risk_model),
            "previous": model_data(model_prev),
        },
        "sources": {
            "current": market_data(ctx.md),
            "previous": previous_sources
            if previous_sources is not None
            else market_data(md_prev)
            if md_prev is not None
            else None,
        },
        "measures": ms,
        "binding": binding,
        "idio_binding": ms[binding]["idio_kf"] if binding else None,
        "is_synthetic": ctx.md.is_synthetic,
        "data_notice": ctx.md.manifest.data_notice,
    }


def path(track, session: date) -> Path:
    return track.root / FOLDER / f"{session}.json"


def binding(record, track) -> dict:
    return {
        "track_event": track.audit_event,
        "session": str(record.date),
        "record_hash": record.record_hash,
        "sidecar_sha256": record.input_hashes[MARKER],
    }


def event_type(track, *, prepared: bool = False) -> str:
    return (PREPARED_EVENT if prepared else EVENT) + (
        "_SHADOW" if track.audit_event.endswith("_SHADOW") else ""
    )


def _events(track, record, *, prepared=False):
    h = sha256_obj(binding(record, track))
    return [
        e
        for e in track.audit.events()
        if e.event_type == event_type(track, prepared=prepared) and e.payload_hash == h
    ]


def load(track, record, *, require_event: bool = True) -> dict | None:
    if MARKER not in record.input_hashes:
        return None
    chain_ok, reason = track.audit.verify_chain()
    if not chain_ok:
        raise ValueError("trilha do diagnóstico inválida: " + reason)
    p = path(track, record.date)
    if not p.is_file() or sha256_file(p) != record.input_hashes[MARKER]:
        raise ValueError(f"{record.date}: diagnóstico diário ausente/adulterado")
    obj = json.loads(p.read_text())
    if obj.get("policy") != POLICY or obj.get("session") != str(record.date):
        raise ValueError("contrato/data do diagnóstico diário inválido")
    if record.compute_hash() != record.record_hash:
        raise ValueError("registro diário adulterado")
    if len(_events(track, record, prepared=True)) != 1:
        raise ValueError(f"{record.date}: selo preparatório ausente/duplicado")
    if require_event:
        if len(_events(track, record)) != 1:
            raise ValueError(f"{record.date}: vínculo do diagnóstico diário ausente/duplicado")
    return obj


def _repair_track_tail(track, record) -> None:
    """Completa somente append interrompido, com JSON/hash já autenticados na preparação.

    Um CSV parcial ou divergente é recusado. Nenhum byte existente é reescrito.
    """
    records = track.records()
    if not records or records[-1].record_hash != record.record_hash:
        if track.tail_problems():
            raise ValueError("recuperação permitida somente na cauda do registro")
        return
    prev = None
    for r in records:
        expected_prev = prev.record_hash if prev else GENESIS_RECORD_HASH
        if r.compute_hash() != r.record_hash or r.prev_record_hash != expected_prev:
            raise ValueError("cadeia diária inválida na recuperação")
        if prev and r.date <= prev.date or record_consistency(r, prev):
            raise ValueError("datas/identidades inválidas na recuperação")
        if r.date != record.date and sha256_obj(r.record_hash) not in track._audited_hashes():
            raise ValueError("registro anterior não autenticado")
        prev = r
    rows = track._csv_rows()
    if len(rows) not in (len(records), len(records) - 1):
        raise ValueError("CSV não é prefixo recuperável do registro")
    for row, r in zip(rows, records, strict=False):
        expected = {c: _cell(record_summary(r)[c]) for c in CSV_COLUMNS}
        if row != expected:
            raise ValueError("CSV divergente na recuperação")
    if track.csv_path.exists() and track.csv_path.stat().st_size:
        if not track.csv_path.read_bytes().endswith(b"\n"):
            raise ValueError("CSV parcial na recuperação")
    h = sha256_obj(record.record_hash)
    events = [
        e for e in track.audit.events() if e.event_type == track.audit_event and e.payload_hash == h
    ]
    if len(events) > 1:
        raise ValueError("evento diário duplicado na recuperação")
    if len(rows) == len(records) - 1:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        if not track.csv_path.exists() or track.csv_path.stat().st_size == 0:
            writer.writerow(CSV_COLUMNS)
        row = record_summary(record)
        writer.writerow([_cell(row[c]) for c in CSV_COLUMNS])
        with track.csv_path.open("a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
    if not events:
        track.audit.append(
            track.audit_event,
            track.actor,
            record.record_hash,
            f"Recuperação do registro diário previamente selado em {record.date}",
            week=record.live_book_week,
        )


def recover(track, record) -> None:
    if MARKER not in record.input_hashes:
        return
    load(track, record, require_event=False)
    _repair_track_tail(track, record)
    problems = track.tail_problems(record) if track.last().date == record.date else []
    if problems:
        raise ValueError("registro não selado: " + "; ".join(problems))
    found = _events(track, record)
    if len(found) > 1:
        raise ValueError("vínculo diário duplicado")
    if not found:
        track.audit.append(
            event_type(track),
            track.actor,
            binding(record, track),
            f"Risco base/evento da carteira efetiva em {record.date}",
            week=record.date,
        )


def append(track, record, diagnostic: dict) -> None:
    p = path(track, record.date)
    raw = text(diagnostic)
    if sha256_text(raw) != record.input_hashes[MARKER]:
        raise ValueError("diagnóstico não corresponde ao registro")
    if p.exists():
        if p.read_text() != raw:
            raise ValueError("diagnóstico órfão divergente na recuperação")
    else:
        write_exclusive(p, raw)
    prepared = _events(track, record, prepared=True)
    if len(prepared) > 1:
        raise ValueError("selo preparatório duplicado")
    if not prepared:
        track.audit.append(
            event_type(track, prepared=True),
            track.actor,
            binding(record, track),
            f"Preparação selada do risco diário em {record.date}",
            week=record.date,
        )
    track.append(record)
    recover(track, record)


def verify(track, *, market_loader=None, market_root=None) -> list[str]:
    problems = []
    expected = set()
    for record in track.records():
        if MARKER not in record.input_hashes:
            continue
        expected.add(path(track, record.date))
        try:
            obj = load(track, record)
            cfg = FundConfig.model_validate(obj["config"])
            from ..contracts import SnapshotManifest

            manifest = SnapshotManifest.model_validate(obj["sources"]["current"]["manifest"])
            if manifest.content_hash() != record.input_hashes["market_data"]:
                raise ValueError("manifesto não corresponde ao registro diário")
            if (
                sha256_obj(obj["config"]) != record.input_hashes["config"]
                or obj["config_hash"] != record.input_hashes["config"]
                or obj["config_bytes_sha256"] != sha256_text(text(obj["config"]))
            ):
                raise ValueError("configuração do diagnóstico não confere")
            weights = {}
            for p in record.positions:
                if p.market_value_usd:
                    weights[p.issuer_id] = (
                        weights.get(p.issuer_id, 0.0) + p.market_value_usd / record.nav_end_usd
                    )
            if obj["weights"] != weights or obj["nav_usd"] != record.nav_end_usd:
                raise ValueError("diagnóstico não usa carteira/NAV efetivos")
            w = pd.Series(obj["weights"], dtype=float)
            models = {n: restore(v) if v else None for n, v in obj["models"].items()}
            if models["base"] is not None and models["base"].as_of != record.date:
                raise ValueError("modelo base não usa a sessão do registro")
            previous = [r for r in track.records() if r.date < record.date]
            if models["previous"] is not None and (
                not previous or models["previous"].as_of != previous[-1].date
            ):
                raise ValueError("modelo anterior não usa o corte do registro anterior")
            if models["previous"] is not None and MARKER in previous[-1].input_hashes:
                prior = load(track, previous[-1])
                if (
                    obj["models"]["previous"] != prior["models"]["base"]
                    or obj["sources"]["previous"] != prior["sources"]["current"]
                ):
                    raise ValueError("modelo/fonte anterior não são os arquivados no próprio corte")
            for data in obj["models"].values():
                if data is not None:
                    if any(
                        sha256_text(text(data[k])) != data["matrix_hashes"][k]
                        for k in ("B", "F", "D")
                    ):
                        raise ValueError("hash integral B/F/D não confere")
                    if date.fromisoformat(data["as_of"]) > record.date:
                        raise ValueError("modelo futuro no diagnóstico")
                    fr = pd.to_datetime(data["factor_returns"]["index"])
                    if len(fr) and fr.max().date() > date.fromisoformat(data["as_of"]):
                        raise ValueError("retorno fatorial após o corte do modelo")
                    if len(set(data["B"]["columns"])) != len(data["B"]["columns"]):
                        raise ValueError("fator duplicado na base")
            required = ["macro:" + s for s in cfg.risk_model.macro_factors]
            if required != obj["required_macro"]:
                raise ValueError("exigência macro mudou")
            cutoffs = {
                "base_as_of": str(models["base"].as_of) if models["base"] else None,
                "previous_base_as_of": str(models["previous"].as_of)
                if models["previous"]
                else None,
                "event_session": str(record.date),
                "returns_through": str(record.date),
            }
            if obj["cutoffs"] != cutoffs:
                raise ValueError("cortes do diagnóstico não conferem")
            from ..portfolio.optimizer import metodologia_ativa

            k, info = (
                kappa_f(models["base"], cfg)
                if models["base"] is not None and metodologia_ativa(cfg)
                else (1.0, {"mode": "legado"})
            )
            if k != obj["kappa_f"] or info != obj["kappa_info"]:
                raise ValueError("κ_F arquivado não recalcula na base")
            for n in ("base", "evento"):
                if measures(models[n], w, required, obj["kappa_f"]) != obj["measures"][n]:
                    raise ValueError("medidas base/evento não recalculam")
            if models["base"] is not None:
                event_model = apply_event_windows(
                    models["base"], pd.Series(obj["countries"]), cfg, record.date
                )
                if model_data(event_model) != obj["models"]["evento"]:
                    raise ValueError("evento não é derivado da base uma vez")
            ms = obj["measures"]
            selected = (
                min(ms, key=lambda n: ms[n]["idio_kf"])
                if all(v["complete"] and v["idio_kf"] is not None for v in ms.values())
                else None
            )
            if obj["binding"] != selected or obj["idio_binding"] != (
                ms[selected]["idio_kf"] if selected else None
            ):
                raise ValueError("base vinculante não confere")
            if not weights:
                expected_risk = {"vol": 0.0, "factor_vol": 0.0, "specific_vol": 0.0}
            elif ms["evento"]["complete"] or required:
                expected_risk = ms["evento"]
            else:
                expected_risk = None  # contrato legado de risco parcial, explicitado no anexo
            if expected_risk is not None:
                for field, attr in (
                    ("vol", "ex_ante_vol"),
                    ("factor_vol", "factor_vol"),
                    ("specific_vol", "specific_vol"),
                ):
                    observed = getattr(record.risk, attr)
                    wanted = expected_risk[field]
                    if (
                        (observed is None) != (wanted is None)
                        or observed is not None
                        and not math.isclose(observed, wanted, rel_tol=1e-12, abs_tol=1e-14)
                    ):
                        raise ValueError("DailyRisk não confere com o modelo de evento efetivo")
            if market_loader is not None:
                md = market_loader(as_of=record.date).truncate(record.date)
                if market_data(md) != obj["sources"]["current"]:
                    raise ValueError("fontes/metadados de mercado não conferem com corte diário")
                if models["previous"] is not None:
                    prev_date = models["previous"].as_of
                    previous = market_loader(as_of=prev_date).truncate(prev_date)
                    if market_data(previous) != obj["sources"]["previous"]:
                        raise ValueError("fontes anteriores não conferem com o próprio corte")
            if market_root is not None:
                root = Path(market_root).resolve()
                for source in obj["sources"].values():
                    if source is None:
                        continue
                    for f in source["manifest"]["files"]:
                        p = (root / f["path"]).resolve()
                        if (
                            not p.is_relative_to(root)
                            or not p.is_file()
                            or sha256_file(p) != f["sha256"]
                        ):
                            raise ValueError("arquivo original de mercado ausente/adulterado")
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            problems.append(f"{record.date}: {exc}")
    folder = track.root / FOLDER
    if folder.is_dir():
        problems += [
            f"diagnóstico órfão: {p.name}" for p in folder.glob("*.json") if p not in expected
        ]
    known = {sha256_obj(binding(r, track)) for r in track.records() if MARKER in r.input_hashes}
    if any(
        e.event_type in (event_type(track), event_type(track, prepared=True))
        and e.payload_hash not in known
        for e in track.audit.events()
    ):
        problems.append("vínculo de diagnóstico órfão na trilha")
    return problems


def read_measures(track, *, market_loader=None, market_root=None) -> dict[date, dict]:
    """Projeção autenticada; sem escrita e sem reinterpretar κ pelo mandato atual."""
    valid, errors = track.verify()
    errors += verify(track, market_loader=market_loader, market_root=market_root)
    if not valid or errors:
        raise ValueError("risco diário não autenticado: " + "; ".join(errors))
    return {r.date: load(track, r) for r in track.records() if MARKER in r.input_hashes}
