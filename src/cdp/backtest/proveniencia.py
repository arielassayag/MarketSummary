"""Governança temporal do replay, sem transformar um retrato atual em PIT.

Um ``MarketData`` real sozinho não autentica vintages. ``FileVintageSource`` pode
verificar uma captura antiga com ``temporal_evidence.json`` (schema abaixo),
arquivos íntegros e disponibilidade anterior ao corte. O registro não pode
retrodatá-la: disponibilidade >= criação/captura das fontes e do registro.
E2 continua exigindo capturas reais e governança por dependência.
"""

from __future__ import annotations

import json
import weakref
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..contracts import SnapshotManifest
from ..data.snapshot import load_snapshot, read_manifest, verify_files
from ..hashing import sha256_file, sha256_obj
from ..market import MarketData
from ..universe import Universe

MODES = frozenset({"simulado", "sombra_real", "pit_auditado"})
SCHEMA = "cdp.replay.temporal/v1"
EVIDENCE_SCHEMA = "cdp.replay.temporal_evidence/v1"
EVIDENCE_FILE = "temporal_evidence.json"
# Cada dependência exige prova própria, mesmo quando compartilha o arquivo.
DEPENDENCIES = {
    "prices": "prices.parquet", "adjusted_prices": "prices.parquet",
    "volume": "prices.parquet", "fx": "fx.parquet",
    "benchmarks": "benchmarks.parquet", "rates": "rates.parquet",
    "fundamentals": "fundamentals.parquet", "short_interest": "short_interest.parquet",
    "lending": "lending.parquet", "universe": "universe.csv",
    "listing_adr_actions": "universe.csv", "consensus_events": "fundamentals.parquet",
    "style_capitalization": "fundamentals.parquet", "news": "news.jsonl",
}
SERIES = ("close", "adj_close", "volume", "fx", "benchmarks", "rates")
FIELDS = {
    "prices": {"close"}, "adjusted_prices": {"adj_close"}, "volume": {"volume"},
    "fx": {"usd_per_unit"}, "benchmarks": {"close"}, "rates": {"value"},
    "fundamentals": {"market_cap", "shares_outstanding"},
    "short_interest": {"shares_short", "short_interest_date"},
    "lending": {"lending_rate_annual", "lending_date"},
    "universe": {"issuer_id", "yahoo_ticker", "currency"},
    "listing_adr_actions": {"adr_ratio", "primary_line", "exchange"},
    "consensus_events": {"forward_eps", "target_mean_price", "next_earnings_date"},
    "style_capitalization": {"market_cap", "shares_outstanding", "book_value"},
    "news": {"published_at"},
}


class TemporalEvidenceError(ValueError):
    """Run incompleto; não autoriza downgrade nem imputação de campos ausentes."""

    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _instant(value: datetime | str) -> datetime:
    v = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(v, datetime) or v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("O corte/disponibilidade precisa de datetime com fuso.")
    return v


def _check_mode(md: MarketData, mode: str, cutoff: datetime) -> None:
    _instant(cutoff)
    if mode not in MODES:
        raise ValueError(f"Modo desconhecido: {mode!r}; use {sorted(MODES)}.")
    if (mode == "simulado") != md.is_synthetic:
        raise TemporalEvidenceError("Modo e origem simulada divergem; não relabelar cotações reais.")
    if md.is_synthetic and ("DADOS SIMULADOS" not in md.manifest.data_notice.upper()
                            or any(not n.is_synthetic for n in md.news)):
        raise TemporalEvidenceError("Simulação sem aviso ou com notícias reais misturadas.")


def _frame_payload(df: pd.DataFrame) -> dict:
    # repr conserva a precisão do float e distingue NaN/None/inf; não altera a
    # tabela nem toma attrs como prova. O driver arquiva também bytes originais.
    return {"index": [repr(v) for v in df.index], "columns": [repr(v) for v in df.columns],
            "dtypes": [str(v) for v in df.dtypes],
            "data": [[repr(v) for v in row] for row in df.itertuples(index=False, name=None)]}


def _data_fingerprint(md: MarketData) -> str:
    return sha256_obj({"tables": {k: _frame_payload(getattr(md, k)) for k in
                                 (*SERIES, "fundamentals", "short_interest", "lending")},
                       "universe_lines": _frame_payload(md.universe.lines),
                       "universe_issuers": _frame_payload(md.universe.issuers),
                       "news": [n.model_dump(mode="json") for n in md.news]})


@dataclass(frozen=True)
class _VerifiedCapture:
    path: Path
    manifest_sha256: str
    evidence_sha256: str
    fingerprint: str
    origin_manifest: SnapshotManifest


# Prova não é aceita por attrs/bool escritos pelo chamador. O leitor de arquivos
# registra só objetos que acabou de verificar; weakref evita reciclagem de ids.
_CAPTURES: dict[int, tuple[weakref.ReferenceType, _VerifiedCapture]] = {}
_ORIGINS: dict[int, tuple[weakref.ReferenceType, SnapshotManifest]] = {}


def _register_origin(md: MarketData, origin: SnapshotManifest) -> None:
    key = id(md)
    _ORIGINS[key] = (weakref.ref(md, lambda _: _ORIGINS.pop(key, None)), origin)


def _origin(md: MarketData) -> SnapshotManifest:
    proof = _capture(md)
    if proof:
        return proof.origin_manifest
    entry = _ORIGINS.get(id(md))
    return entry[1] if entry and entry[0]() is md else md.manifest


def _register(md: MarketData, proof: _VerifiedCapture) -> None:
    key = id(md)
    ref = weakref.ref(md, lambda _: _CAPTURES.pop(key, None))
    _CAPTURES[key] = (ref, replace(proof, fingerprint=_data_fingerprint(md)))


def _capture(md: MarketData) -> _VerifiedCapture | None:
    entry = _CAPTURES.get(id(md))
    return entry[1] if entry and entry[0]() is md else None


def _evidence(md: MarketData, cutoff: datetime) -> tuple[dict, list[str]]:
    proof = _capture(md)
    if proof is None:
        return {}, ["captura histórica/registro por dependência não autenticados"]
    try:
        if sha256_file(proof.path / "manifest.json") != proof.manifest_sha256:
            raise ValueError("manifesto da captura alterado")
        if sha256_file(proof.path / EVIDENCE_FILE) != proof.evidence_sha256:
            raise ValueError("registro temporal alterado")
        if sha256_obj(read_manifest(proof.path)) != sha256_obj(proof.origin_manifest):
            raise ValueError("metadados originais da captura alterados em memória")
        verify_files(proof.path, proof.origin_manifest)
        if _data_fingerprint(md) != proof.fingerprint:
            raise ValueError("tabelas/universo da captura alterados em memória")
        raw = json.loads((proof.path / EVIDENCE_FILE).read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("dependencies"), dict):
            raise ValueError("registro temporal sem mapa de dependências")
        if raw.get("schema_version") != EVIDENCE_SCHEMA:
            raise ValueError("schema de prova não suportado")
        if raw.get("manifest_sha256") != proof.manifest_sha256:
            raise ValueError("prova ligada a outro manifesto")
        at = _instant(raw["registered_at"])
        if at > cutoff:
            raise ValueError("registro temporal só disponível depois do corte")
        return raw, []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {}, [f"prova temporal inválida: {exc}"]


def assess_temporal_inputs(md: MarketData, cutoff: datetime, mode: str) -> dict:
    """Diagnóstico conservador por dependência; não escreve nem faz rede.

    ``point_in_time=True``, period_end, publication_date isolada ou attrs não
    substituem a prova. A ausência de prova retorna ``complete=False`` no real.
    O modo auditado é recusado por ``prefix_market``; nunca vira sombra sozinho.
    """
    _check_mode(md, mode, cutoff)
    raw, common = ({}, []) if md.is_synthetic else _evidence(md, cutoff)
    proof = _capture(md)
    origin = _origin(md)
    available_floor = max([origin.created_at] + [s.retrieved_at for s in origin.sources]
                          + ([_instant(raw["registered_at"])] if raw else []))
    files = {f.path: f.sha256 for f in origin.files}
    sources = {s.source_id: s for s in origin.sources}
    deps: dict[str, dict[str, Any]] = {}
    for dep, basename in DEPENDENCIES.items():
        reasons = list(common)
        evidence = raw.get("dependencies", {}).get(dep) if raw else None
        if md.is_synthetic:
            deps[dep] = {"status": "simulado", "reasons": ["DADOS SIMULADOS"],
                         "available_at": None}
            continue
        if available_floor > cutoff:
            reasons.append("captura/criação/fonte posterior ao corte; período contábil não é disponibilidade")
        if not origin.sources:
            reasons.append("fontes originais ausentes")
        if evidence is None:
            reasons.append("prova de vintage/campos por dependência ausente")
        else:
            try:
                known = _instant(evidence["available_at"])
                if known < available_floor or known > cutoff:
                    reasons.append("disponibilidade retrodatada ou posterior ao corte")
                bindings = evidence["files"]
                if not isinstance(bindings, dict):
                    raise TypeError("arquivos da prova precisam de mapa de SHA")
                if not bindings or not any(Path(k).name == basename for k in bindings):
                    reasons.append("arquivo do insumo não está vinculado à prova")
                if any(files.get(k) != v for k, v in bindings.items()):
                    reasons.append("SHA/arquivo da prova não confere com a captura")
                ids = evidence["source_ids"]
                if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
                    raise TypeError("fonte da prova precisa de lista de ids")
                if not ids or any(i not in sources for i in ids):
                    reasons.append("fonte da dependência ausente/não vinculada")
                fields = set(evidence.get("fields", []))
                authenticated_fields = {f for i in ids if i in sources for f in sources[i].fields}
                if not FIELDS[dep] <= fields or not fields <= authenticated_fields:
                    reasons.append("campos essenciais não vinculados aos campos das fontes originais")
                if evidence.get("kind") != "captured_vintage":
                    reasons.append("tipo de prova não suportado; publicação isolada não autentica tabela")
                # Essas semânticas precisam de declaração arquivada específica;
                # um arquivo genérico de preços/fundamentos não as comprova.
                if dep in {"adjusted_prices", "listing_adr_actions", "style_capitalization",
                           "consensus_events"} and evidence.get("scope") != dep:
                    reasons.append("ajustes/classes/capitalização/consenso sem escopo temporal explícito")
            except (KeyError, TypeError, ValueError):
                reasons.append("prova por dependência ilegível/incompleta")
        if dep in {"universe", "listing_adr_actions"} and (
                not md.universe.source_sha256 or origin.universe_sha256 != md.universe.source_sha256):
            reasons.append("universo não corresponde à origem autenticada")
        if origin.provisional_dates and any(d <= md.as_of for d in origin.provisional_dates):
            reasons.append("há barra provisória no intervalo")
        deps[dep] = {"status": "nao_pit" if reasons else "captura_verificada",
                     "reasons": sorted(set(reasons)),
                     "available_at": evidence.get("available_at") if isinstance(evidence, dict) else None}
    non_pit = [k for k, v in deps.items() if v["status"] == "nao_pit"]
    result = {"schema_version": SCHEMA, "mode": mode, "cutoff": cutoff.isoformat(),
              "as_of": md.as_of.isoformat(), "is_synthetic": md.is_synthetic,
              "origin_manifest_sha256": proof.manifest_sha256 if proof else sha256_obj(origin),
              "origin_files": files, "data_fingerprint": _data_fingerprint(md),
              "evidence_sha256": proof.evidence_sha256 if proof else None,
              "dependencies": deps, "non_pit_dependencies": non_pit,
              "complete": not non_pit,
              "limitation": "PIT cobre a captura verificada; não inventa vintage/publicação nem ajusta preços finais."}
    result["knowledge_sha256"] = sha256_obj(result)
    return result


def prefix_market(md: MarketData, as_of: date, knowledge_cutoff: datetime,
                  mode: str) -> MarketData:
    """Copia/corta séries e notícias; retratos lentos conservam origem e lacunas.

    Não seleciona publicação por period_end, não remove campos para forçar gates
    e não muda dados reais para simulados. SHA de conhecimento fica nas limitações
    do manifesto derivado; o driver deve arquivar também o diagnóstico completo.
    """
    _check_mode(md, mode, knowledge_cutoff)
    if as_of > md.as_of or as_of > knowledge_cutoff.date():
        raise TemporalEvidenceError("Prefixo pede data futura ao mercado ou ao corte de conhecimento.")
    ts = pd.Timestamp(as_of)
    tables = {k: getattr(md, k).loc[getattr(md, k).index <= ts].copy(deep=True) for k in SERIES}
    tables.update({k: getattr(md, k).copy(deep=True) for k in
                   ("fundamentals", "short_interest", "lending")})
    universe = Universe(md.universe.lines.copy(deep=True), md.universe.issuers.copy(deep=True),
                        md.universe.source_sha256)
    out = replace(md, **tables, universe=universe,
                  manifest=md.manifest.model_copy(update={"as_of": as_of}),
                  news=tuple(n for n in md.news if n.published_at <= knowledge_cutoff
                             and n.published_at.date() <= as_of))
    origin = _origin(md)
    _register_origin(out, origin)
    proof = _capture(md)
    if proof:
        # Valida o original antes de registrar uma nova visão; não lava alterações.
        _, errors = _evidence(md, knowledge_cutoff)
        if not errors:
            _register(out, proof)
    assessment = assess_temporal_inputs(out, knowledge_cutoff, mode)
    if mode == "pit_auditado" and not assessment["complete"]:
        raise TemporalEvidenceError("PIT incompleto: " + ", ".join(assessment["non_pit_dependencies"]),
                                    assessment)
    limitations = list(md.manifest.limitations) + [
        f"Replay {mode}: corte {knowledge_cutoff.isoformat()}; prefixo {as_of}; conhecimento SHA-256 "
        f"{assessment['knowledge_sha256']}; origem e retratos lentos preservados.",
    ]
    if assessment["non_pit_dependencies"]:
        limitations.append("Dependências não PIT: " + ", ".join(assessment["non_pit_dependencies"]))
    out = replace(out, manifest=out.manifest.model_copy(update={
        "snapshot_id": f"replay-{md.manifest.snapshot_id}-{assessment['knowledge_sha256'][:16]}",
        "limitations": limitations,
        "provisional_dates": [d for d in md.manifest.provisional_dates if d <= as_of],
    }))
    _register_origin(out, origin)
    if proof and _capture(out) is None and not _evidence(md, knowledge_cutoff)[1]:
        _register(out, proof)
    return out


class FileVintageSource:
    """Fonte local de snapshots completos: nunca escolhe base futura.

    Registro opcional ``temporal_evidence.json``: schema_version, registered_at,
    manifest_sha256 e dependencies. Cada dependência contém kind=captured_vintage,
    available_at, files={path:SHA}, source_ids, fields e scope para semânticas especiais.
    O registro também precisa existir antes do corte; escrito hoje não certifica
    uma captura histórica retroativamente. Publicações/vintages por linha ainda
    não representados são recusados, sem rede ou imputação.
    """

    def __init__(self, root: Path | str, *, mode: str, knowledge_cutoff: datetime):
        if mode not in MODES:
            raise ValueError("Modo de replay desconhecido.")
        self.root = Path(root)
        self.mode = mode
        self.knowledge_cutoff = _instant(knowledge_cutoff)

    def load(self, as_of: date, *, knowledge_cutoff: datetime | None = None) -> MarketData:
        cutoff = _instant(knowledge_cutoff or self.knowledge_cutoff)
        paths = ([self.root] if (self.root / "manifest.json").exists() else
                 sorted(p.parent for p in self.root.glob("*/manifest.json")))
        eligible = []
        for p in paths:
            m = read_manifest(p)
            latest = max([m.created_at] + [s.retrieved_at for s in m.sources])
            if m.as_of <= as_of and latest <= cutoff:
                eligible.append((m.as_of, latest, p))
        if not eligible:
            raise TemporalEvidenceError("Sem captura/base elegível anterior à data e ao corte; run incompleto.")
        p = max(eligible)[2]
        md = load_snapshot(p, verify=True)
        if (p / EVIDENCE_FILE).is_file():
            proof = _VerifiedCapture(p, sha256_file(p / "manifest.json"),
                                     sha256_file(p / EVIDENCE_FILE), "", md.manifest)
            _register(md, proof)
        return prefix_market(md, as_of=min(as_of, md.as_of), knowledge_cutoff=cutoff, mode=self.mode)


__all__ = ["TemporalEvidenceError", "assess_temporal_inputs", "prefix_market", "FileVintageSource"]
