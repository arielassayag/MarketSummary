"""Importação de pesquisa externa (analistas humanos ou agentes com pesquisa na web).

O arquivo JSON tem a forma ``{"notes": [ResearchNote...], "macro": [MacroNote...],
"views": [View...]}``. Nada é confiado sem verificação:

- cada nota/nota macro é validada pelo contrato Pydantic e por TODOS os guardrails de texto
  (números fora de placeholders, fatos inexistentes ou de outro emissor, fatos usados sem
  citação, padrões de injeção);
- evidências precisam existir: ``fact`` no FactBook da semana, ``news`` na lista de notícias
  fornecida, ``source`` como URL ``http(s)``;
- o provedor de cada nota recebe o prefixo ``imported:`` (procedência visível como IA/externo);
  papel ``pm`` e escopo de governança não podem ser importados;
- visões embutidas NUNCA são confiadas: inclinações são recalculadas a partir das notas
  validadas; só restrições puras (``no_short``/``no_long``/``max_abs_weight`` dentro do mandato,
  score 0) são aceitas — a IA só aperta. Visões do gestor ou que ampliem limites são rejeitadas.

Notas inválidas são descartadas e os motivos voltam na lista de problemas.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterable
from datetime import UTC, date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ...config import FundConfig
from ...contracts import (
    EvidenceKind,
    EvidenceRef,
    FactBook,
    MacroNote,
    NewsItem,
    ResearchNote,
    ResearchPack,
    View,
    ViewSource,
)
from ...hashing import sha256_obj
from ..guardrails import (
    check_placeholders,
    currency_claim_issues,
    detect_injection,
    extract_fact_ids,
    find_free_numbers,
    sanitize_untrusted,
    text_format_issues,
)

IMPORTED_PREFIX = "imported:"
IMPORTED_PACK_PROVIDER = "imported"
RESERVED_SCOPES = frozenset({"GOVERNANÇA", "GOVERNANCA"})


def _prefixed(provider: object) -> str:
    p = str(provider or "externo").strip() or "externo"
    return p if p.startswith(IMPORTED_PREFIX) else f"{IMPORTED_PREFIX}{p}"


def _validation_summary(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])


def _is_http_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _text_problems(label: str, text: str, fb: FactBook, issuer_id: str | None,
                   cited_facts: set[str]) -> list[str]:
    out: list[str] = []
    terms = [issuer_id] if issuer_id else []
    nums = find_free_numbers(text, terms)
    if nums:
        out.append(f"{label}: número fora de placeholder {nums}")
    unknown = check_placeholders(text, fb)
    if unknown:
        out.append(f"{label}: fato inexistente {unknown}")
    known = [f for f in extract_fact_ids(text) if f in fb.facts]
    foreign = [f for f in known if issuer_id and fb.facts[f].issuer_id not in (None, issuer_id)]
    if foreign:
        out.append(f"{label}: fato de outro emissor {foreign}")
    uncited = [f for f in known if f not in cited_facts]
    if uncited:
        out.append(f"{label}: fato usado sem citação como evidência {uncited}")
    out += text_format_issues(label, text)
    out += currency_claim_issues(label, text, fb)
    inj = detect_injection(text)
    if inj:
        out.append(f"{label}: padrão de injeção {inj}")
    return out


def _evidence_problems(label: str, evidence: Iterable[EvidenceRef], fb: FactBook,
                       news_ids: set[str]) -> list[str]:
    out = []
    for ref in evidence:
        if ref.kind == EvidenceKind.FACT and ref.ref_id not in fb.facts:
            out.append(f"{label}: fato de evidência inexistente {ref.ref_id!r}")
        elif ref.kind == EvidenceKind.NEWS and ref.ref_id not in news_ids:
            out.append(f"{label}: notícia de evidência não verificável {ref.ref_id!r}")
        elif ref.kind == EvidenceKind.SOURCE and not _is_http_url(ref.ref_id):
            out.append(f"{label}: fonte precisa ser URL http(s) {ref.ref_id!r}")
    return out


def _meta_problems(label: str, values: dict[str, str | None]) -> list[str]:
    """Metadados exibidos (ids, autor, modelo): sem marcação, URL ou padrão de injeção."""
    out: list[str] = []
    for key, value in values.items():
        if not value:
            continue
        out += text_format_issues(f"{label}.{key}", value)
        inj = detect_injection(value)
        if inj:
            out.append(f"{label}.{key}: padrão de injeção {inj}")
    return out


def _note_texts(note: ResearchNote) -> list[tuple[str, str]]:
    items = [("thesis", note.thesis)]
    items += [(f"bull_points[{i}]", t) for i, t in enumerate(note.bull_points)]
    items += [(f"bear_points[{i}]", t) for i, t in enumerate(note.bear_points)]
    items += [(f"catalysts[{i}]", c.description) for i, c in enumerate(note.catalysts)]
    items += [(f"key_risks[{i}]", t) for i, t in enumerate(note.key_risks)]
    if note.squeeze is not None:
        items.append(("squeeze.rationale", note.squeeze.rationale))
    items += [(f"evidence[{i}].note", e.note) for i, e in enumerate(note.evidence) if e.note]
    return items


def _macro_texts(note: MacroNote) -> list[tuple[str, str]]:
    items = [("regime", note.regime), ("summary", note.summary)]
    items += [(f"key_events[{i}]", c.description) for i, c in enumerate(note.key_events)]
    items += [(f"risks[{i}]", t) for i, t in enumerate(note.risks)]
    items += [(f"portfolio_implications[{i}]", t)
              for i, t in enumerate(note.portfolio_implications)]
    items += [(f"evidence[{i}].note", e.note) for i, e in enumerate(note.evidence) if e.note]
    return items


def _prepare(raw: dict[str, Any], week: date, fb: FactBook) -> dict[str, Any]:
    data = dict(raw)
    data["provider"] = _prefixed(data.get("provider"))
    data.setdefault("week", week.isoformat())
    data.setdefault("prompt_version", "importado")
    data["is_synthetic"] = bool(data.get("is_synthetic", False)) or fb.is_synthetic
    return data


def _validate_model(model: type[BaseModel], data: dict[str, Any], label: str,
                    issues: list[str]) -> BaseModel | None:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        issues.append(f"{label}: rejeitada (schema): {_validation_summary(exc)}")
        return None


def load_imported_pack(path: Path, week: date, snapshot_id: str, factbook: FactBook,
                       as_of: date, *, cfg: FundConfig | None = None,
                       news: Iterable[NewsItem] | None = None) -> tuple[ResearchPack, list[str]]:
    """Lê, valida e filtra um pacote de pesquisa externo. Retorna ``(pacote, problemas)``.

    ``as_of`` é o último pregão permitido para as evidências: notícias publicadas depois
    dele tornam a nota inválida (look-ahead). Arquivo inexistente ⇒ ``FileNotFoundError``.
    """
    from ..agents import merge_views, notes_to_views  # import tardio (evita ciclo)

    cfg = cfg or FundConfig()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pacote de pesquisa importado não encontrado: {path}")
    issues: list[str] = []
    empty = ResearchPack(week=week, snapshot_id=snapshot_id, provider=IMPORTED_PACK_PROVIDER,
                         is_synthetic=factbook.is_synthetic)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return empty, [f"Arquivo importado ilegível (JSON inválido): {exc}"]
    if not isinstance(payload, dict):
        return empty, ["Arquivo importado precisa ser um objeto JSON com notes/macro/views."]
    extra = sorted(set(payload) - {"notes", "macro", "views"})
    if extra:
        issues.append(f"Chaves desconhecidas ignoradas: {extra}")

    news_items = {n.news_id: n for n in (news or [])}
    usable_news: dict[str, NewsItem] = {}
    for nid, n in news_items.items():
        if n.published_at.astimezone(UTC).date() > as_of:
            continue
        title, flags = sanitize_untrusted(n.title)
        if any(f.startswith("injecao:") for f in flags) or not title:
            continue
        usable_news[nid] = n.model_copy(update={"title": title})
    news_ids = set(usable_news)

    notes: list[ResearchNote] = []
    seen: set[str] = set()
    for i, raw in enumerate(payload.get("notes") or []):
        label = f"notes[{i}]"
        if not isinstance(raw, dict):
            issues.append(f"{label}: rejeitada (não é objeto JSON)")
            continue
        label = f"notes[{i}] ({raw.get('note_id', 'sem id')})"
        if raw.get("role") == "pm":
            issues.append(f"{label}: rejeitada (papel 'pm' não pode ser importado)")
            continue
        if raw.get("week") not in (None, week.isoformat()):
            issues.append(f"{label}: rejeitada (semana {raw.get('week')} ≠ {week.isoformat()})")
            continue
        if "created_at" not in raw:
            issues.append(f"{label}: rejeitada (created_at ausente)")
            continue
        data = _prepare(raw, week, factbook)
        data.setdefault("input_hash", sha256_obj(raw))
        note = _validate_model(ResearchNote, data, label, issues)
        if note is None:
            continue
        assert isinstance(note, ResearchNote)
        if note.note_id in seen:
            issues.append(f"{label}: rejeitada (note_id duplicado)")
            continue
        problems = _evidence_problems(label, note.evidence, factbook, news_ids)
        problems += _meta_problems(label, {"note_id": note.note_id, "issuer_id": note.issuer_id,
                                           "provider": note.provider, "model": note.model})
        cited = {e.ref_id for e in note.evidence if e.kind == EvidenceKind.FACT}
        for path_, text in _note_texts(note):
            problems += _text_problems(f"{label}.{path_}", text, factbook, note.issuer_id, cited)
        late = [e.ref_id for e in note.evidence if e.kind == EvidenceKind.NEWS
                and e.ref_id in news_items
                and news_items[e.ref_id].published_at.astimezone(UTC).date() > as_of]
        if late:
            problems.append(f"{label}: evidência publicada após {as_of.isoformat()} {late}")
        if note.stance != 0 and not note.evidence:
            problems.append(f"{label}: stance direcional sem evidência")
        if problems:
            issues += [f"{p} — nota rejeitada" for p in problems]
            continue
        seen.add(note.note_id)
        notes.append(note)

    macro: list[MacroNote] = []
    for i, raw in enumerate(payload.get("macro") or []):
        label = f"macro[{i}]"
        if not isinstance(raw, dict):
            issues.append(f"{label}: rejeitada (não é objeto JSON)")
            continue
        if str(raw.get("scope", "")).strip().upper() in RESERVED_SCOPES:
            issues.append(f"{label}: rejeitada (escopo de governança é reservado ao código)")
            continue
        if "created_at" not in raw:
            issues.append(f"{label}: rejeitada (created_at ausente)")
            continue
        data = _prepare(raw, week, factbook)
        m = _validate_model(MacroNote, data, label, issues)
        if m is None:
            continue
        assert isinstance(m, MacroNote)
        problems = _evidence_problems(label, m.evidence, factbook, news_ids)
        problems += _meta_problems(label, {"note_id": m.note_id, "scope": m.scope,
                                           "provider": m.provider, "model": m.model})
        cited = {e.ref_id for e in m.evidence if e.kind == EvidenceKind.FACT}
        for path_, text in _macro_texts(m):
            problems += _text_problems(f"{label}.{path_}", text, factbook, None, cited)
        if problems:
            issues += [f"{p} — nota macro rejeitada" for p in problems]
            continue
        macro.append(m)

    cap = max(cfg.risk.max_long_weight, cfg.risk.max_short_weight)
    restrictive: list[View] = []
    for i, raw in enumerate(payload.get("views") or []):
        label = f"views[{i}]"
        if not isinstance(raw, dict):
            issues.append(f"{label}: rejeitada (não é objeto JSON)")
            continue
        v = _validate_model(View, dict(raw), label, issues)
        if v is None:
            continue
        assert isinstance(v, View)
        if v.source != ViewSource.AI:
            issues.append(f"{label}: rejeitada (visão do gestor não pode ser importada)")
            continue
        if v.max_abs_weight is not None and v.max_abs_weight > cap:
            issues.append(f"{label}: rejeitada (max_abs_weight acima do teto do mandato — "
                          "visões de IA só podem apertar limites)")
            continue
        if v.score != 0:
            issues.append(f"{label}: inclinação embutida ignorada (recalculada a partir das "
                          "notas validadas)")
            continue
        if not (v.no_short or v.no_long or v.max_abs_weight is not None):
            issues.append(f"{label}: visão sem efeito restritivo ignorada")
            continue
        text_issues = _text_problems(f"{label}.rationale", v.rationale, factbook, v.issuer_id,
                                     set())
        text_issues += _meta_problems(label, {"issuer_id": v.issuer_id, "author": v.author})
        if text_issues:
            issues += [f"{p} — visão rejeitada" for p in text_issues]
            continue
        restrictive.append(v.model_copy(update={"author": _prefixed(v.author),
                                                "confidence": 1.0 if (v.no_short or v.no_long)
                                                else v.confidence}))

    views = merge_views(notes_to_views(notes, cfg) + restrictive)
    referenced = {e.ref_id for n in notes for e in n.evidence if e.kind == EvidenceKind.NEWS}
    referenced |= {e.ref_id for m in macro for e in m.evidence if e.kind == EvidenceKind.NEWS}
    pack = ResearchPack(
        week=week, snapshot_id=snapshot_id, provider=IMPORTED_PACK_PROVIDER,
        notes=sorted(notes, key=lambda n: (n.issuer_id, n.role, n.note_id)),
        macro=sorted(macro, key=lambda m: (m.scope, m.note_id)), views=views,
        news=sorted((usable_news[n] for n in referenced if n in usable_news),
                    key=lambda n: (n.published_at, n.news_id)),
        is_synthetic=factbook.is_synthetic)
    return pack, issues
