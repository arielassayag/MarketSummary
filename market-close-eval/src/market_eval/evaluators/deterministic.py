"""Avaliação determinística (por código) dos outputs — seção 12 da especificação.

Regras de ouro:
- tolerâncias pequenas e explícitas por measure_kind;
- troca de sinal SEMPRE é falha;
- retorno nunca pode ser tratado como contribuição;
- hard_fail quando: JSON/schema inválido; erro de sinal/valor/unidade em fato
  crítico; evidence_id inexistente; retorno como contribuição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import cast

from ..config import ScoringConfig
from ..schemas import AgentOutput, Case, Direction, Fact, MeasureKind

FAILURE_CATEGORIES = [
    "json_invalid",
    "schema_invalid",
    "word_count",
    "headline_length",
    "unknown_fact_id",
    "duplicate_id",
    "key_moves_count",
    "drivers_count",
    "watch_items_count",
    "numeric_mismatch",
    "unit_mismatch",
    "direction_mismatch",
    "measure_kind_mismatch",
    "sign_flip",
    "critical_fact_missing",
    "must_mention_incomplete",
    "claim_evidence_invalid",
    "fact_claim_without_evidence",
    "return_as_contribution",
]

_CONTRIB_RE = re.compile(r"contribui\w*", re.IGNORECASE)
_NUM_UNIT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(%|pontos|pts|bps|pp)", re.IGNORECASE)


@dataclass
class DeterministicGrade:
    case_id: str
    task_id: str
    schema_valid: bool
    length_valid: bool
    word_count: int
    headline_ok: bool
    evidence_id_validity: float  # fração de IDs citados que existem
    key_moves_count_ok: bool
    drivers_count_ok: bool
    critical_fact_recall: float
    must_mention_recall: float
    numeric_accuracy: float
    direction_accuracy: float
    unit_accuracy: float
    measure_kind_accuracy: float
    claim_evidence_coverage: float
    return_as_contribution_violation: bool
    hard_fail: bool
    failure_categories: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "task_id": self.task_id,
            "schema_valid": self.schema_valid,
            "length_valid": self.length_valid,
            "word_count": self.word_count,
            "headline_ok": self.headline_ok,
            "evidence_id_validity": self.evidence_id_validity,
            "key_moves_count_ok": self.key_moves_count_ok,
            "drivers_count_ok": self.drivers_count_ok,
            "critical_fact_recall": self.critical_fact_recall,
            "must_mention_recall": self.must_mention_recall,
            "numeric_accuracy": self.numeric_accuracy,
            "direction_accuracy": self.direction_accuracy,
            "unit_accuracy": self.unit_accuracy,
            "measure_kind_accuracy": self.measure_kind_accuracy,
            "claim_evidence_coverage": self.claim_evidence_coverage,
            "return_as_contribution_violation": self.return_as_contribution_violation,
            "hard_fail": self.hard_fail,
            "failure_categories": self.failure_categories,
            "details": self.details,
        }


def grade_from_dict(row: dict[str, object]) -> DeterministicGrade:
    details = row.get("details")
    cats = row.get("failure_categories")
    return DeterministicGrade(
        case_id=str(row["case_id"]),
        task_id=str(row["task_id"]),
        schema_valid=bool(row["schema_valid"]),
        length_valid=bool(row["length_valid"]),
        word_count=int(cast("int", row["word_count"])),
        headline_ok=bool(row["headline_ok"]),
        evidence_id_validity=float(cast("float", row["evidence_id_validity"])),
        key_moves_count_ok=bool(row["key_moves_count_ok"]),
        drivers_count_ok=bool(row["drivers_count_ok"]),
        critical_fact_recall=float(cast("float", row["critical_fact_recall"])),
        must_mention_recall=float(cast("float", row["must_mention_recall"])),
        numeric_accuracy=float(cast("float", row["numeric_accuracy"])),
        direction_accuracy=float(cast("float", row["direction_accuracy"])),
        unit_accuracy=float(cast("float", row["unit_accuracy"])),
        measure_kind_accuracy=float(cast("float", row["measure_kind_accuracy"])),
        claim_evidence_coverage=float(cast("float", row["claim_evidence_coverage"])),
        return_as_contribution_violation=bool(row["return_as_contribution_violation"]),
        hard_fail=bool(row["hard_fail"]),
        failure_categories=[str(x) for x in cats] if isinstance(cats, list) else [],
        details=details if isinstance(details, dict) else {},
    )


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _value_ok(expected: float | None, got: float | None, tol: float) -> bool:
    if expected is None or got is None:
        return False
    if abs(got - expected) <= tol:
        return True
    return False


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def grade_output(
    case: Case,
    output: AgentOutput | None,
    scoring: ScoringConfig,
    *,
    json_parse_ok: bool = True,
    task_id: str = "",
) -> DeterministicGrade:
    facts_by_id: dict[str, Fact] = {f.fact_id: f for f in case.facts}
    ref = case.reference
    categories: list[str] = []
    details: dict[str, object] = {}
    hard_fail = False

    tol_for: dict[str, float] = dict(scoring.tolerances)

    # 1-2: JSON válido e schema válido (parse já feito no runner; registramos aqui)
    if output is None:
        categories.append("schema_invalid" if json_parse_ok else "json_invalid")
        return DeterministicGrade(
            case_id=case.case_id,
            task_id=task_id,
            schema_valid=False,
            length_valid=False,
            word_count=0,
            headline_ok=False,
            evidence_id_validity=0.0,
            key_moves_count_ok=False,
            drivers_count_ok=False,
            critical_fact_recall=0.0,
            must_mention_recall=0.0,
            numeric_accuracy=0.0,
            direction_accuracy=0.0,
            unit_accuracy=0.0,
            measure_kind_accuracy=0.0,
            claim_evidence_coverage=0.0,
            return_as_contribution_violation=False,
            hard_fail=True,
            failure_categories=categories,
            details={},
        )

    # 3: contagem de palavras
    wc = word_count(output.commentary)
    lo, hi = scoring.word_range
    length_valid = lo <= wc <= hi
    if not length_valid:
        categories.append("word_count")
        details["word_count"] = wc

    # 4: headline
    headline_ok = len(output.headline) <= scoring.headline_max_chars
    if not headline_ok:
        categories.append("headline_length")

    # contagens estruturais (6, 7, watch_items)
    km_lo, km_hi = scoring.limits["key_moves"]
    dr_lo, dr_hi = scoring.limits["drivers"]
    wi_lo, wi_hi = scoring.limits["watch_items"]
    key_moves_count_ok = km_lo <= len(output.key_moves) <= km_hi
    drivers_count_ok = dr_lo <= len(output.drivers) <= dr_hi
    watch_ok = wi_lo <= len(output.watch_items) <= wi_hi
    if not key_moves_count_ok:
        categories.append("key_moves_count")
    if not drivers_count_ok:
        categories.append("drivers_count")
    if not watch_ok:
        categories.append("watch_items_count")

    # 5, 17: IDs existem / duplicados
    cited: list[str] = []
    for km in output.key_moves:
        cited.append(km.fact_id)
    for d in output.drivers:
        cited += d.evidence_ids
    for c in output.claims:
        cited += c.evidence_ids
    known = set(facts_by_id)
    unknown = [i for i in cited if i not in known]
    evidence_id_validity = 1.0 if not cited else sum(1 for i in cited if i in known) / len(cited)
    if unknown:
        # evidence_id/fact_id inexistente é sempre hard fail (seção 14)
        categories.append("unknown_fact_id")
        details["unknown_fact_ids"] = sorted(set(unknown))
        hard_fail = True
    # duplicatas DENTRO da mesma coleção (dois key_moves iguais, ou o mesmo id
    # repetido numa lista de evidência); repetir um id em estruturas distintas é ok
    dupes: list[str] = []
    km_ids = [km.fact_id for km in output.key_moves]
    dupes += [i for i in sorted(set(km_ids)) if km_ids.count(i) > 1]
    for id_list in [d.evidence_ids for d in output.drivers] + [c.evidence_ids for c in output.claims]:
        dupes += [i for i in sorted(set(id_list)) if id_list.count(i) > 1]
    if dupes:
        categories.append("duplicate_id")
        details["duplicate_ids"] = sorted(set(dupes))

    # key_moves: 8-11 (valor, unidade, direção, measure_kind) + sinal + críticos
    n_checked = n_num_ok = n_dir_ok = n_unit_ok = n_mk_ok = 0
    critical_cited: set[str] = set()
    for km in output.key_moves:
        fact = facts_by_id.get(km.fact_id)
        if fact is None:
            hard_fail = True  # ID fabricado
            continue
        if fact.fact_id in ref.critical_fact_ids:
            critical_cited.add(fact.fact_id)
        n_checked += 1
        mk_ok = km.measure_kind == fact.measure_kind.value
        n_mk_ok += int(mk_ok)
        if not mk_ok:
            categories.append("measure_kind_mismatch")
            # retorno apresentado como contribuição (ou vice-versa) é violação grave
            if {km.measure_kind, fact.measure_kind.value} >= {"return_pct", "contribution_bps"}:
                categories.append("return_as_contribution")
                hard_fail = True
        unit_ok = km.unit == fact.unit.value
        n_unit_ok += int(unit_ok)
        if not unit_ok:
            categories.append("unit_mismatch")
        if fact.measure_kind in (MeasureKind.return_pct, MeasureKind.change_pct, MeasureKind.change_bps, MeasureKind.contribution_bps):
            tol = tol_for.get(fact.measure_kind.value, 0.05)
            value_ok = _value_ok(fact.value, km.value, tol)
            n_num_ok += int(value_ok)
            if not value_ok:
                categories.append("numeric_mismatch")
                if fact.fact_id in ref.critical_fact_ids:
                    hard_fail = True
                numeric_errors = details.setdefault("numeric_errors", [])
                if isinstance(numeric_errors, list):
                    numeric_errors.append({"fact_id": fact.fact_id, "expected": fact.value, "got": km.value})
            if km.value is not None and fact.value is not None:
                if _sign(km.value) != _sign(fact.value) and scoring.sign_flip_is_failure:
                    categories.append("sign_flip")
                    if fact.fact_id in ref.critical_fact_ids:
                        hard_fail = True
            dir_ok = km.direction in (fact.direction.value, Direction.na.value)
            n_dir_ok += int(dir_ok)
            if not dir_ok:
                categories.append("direction_mismatch")
        else:
            # não-assinado: presença de valor é verificada só como medida_kind
            n_num_ok += int(km.value == fact.value)
            dir_ok = km.direction in (fact.direction.value, Direction.na.value)
            n_dir_ok += int(dir_ok)
        if km.unit == fact.unit.value and fact.fact_id in ref.critical_fact_ids and not unit_ok:
            pass  # já contabilizado

    # 12: retorno tratado como contribuição. A troca de measure_kind em key_moves
    # já é capturada acima; no TEXTO, hard fail somente quando a palavra acompanha
    # número com unidade (ex.: "contribuiu com -3,53%" / "contribuição de 10 pontos"),
    # que é o confundimento técnico. Menção qualitativa isolada ("contribuiu para o
    # clima") é apenas registrada — o judge avalia a disciplina causal.
    has_contribution_fact = any(f.measure_kind == MeasureKind.contribution_bps for f in case.facts)
    qualitative = bool(_CONTRIB_RE.search(output.commentary))
    if qualitative and not has_contribution_fact:
        numeric_contrib = False
        for m in _CONTRIB_RE.finditer(output.commentary):
            window = output.commentary[m.start() : m.start() + 120]
            if _NUM_UNIT_RE.search(window):
                numeric_contrib = True
                break
        if numeric_contrib:
            categories.append("return_as_contribution")
            hard_fail = True
        else:
            details["contribution_wording_qualitative"] = True

    # 13: fatos críticos aparecem em key_moves ou claims
    claim_ids = {i for c in output.claims for i in c.evidence_ids}
    for fid in ref.critical_fact_ids:
        if fid in claim_ids:
            critical_cited.add(fid)
    critical_fact_recall = (
        len(critical_cited) / len(ref.critical_fact_ids) if ref.critical_fact_ids else 1.0
    )
    if critical_fact_recall < 1.0:
        categories.append("critical_fact_missing")

    # 14: recall de must_mention
    all_cited = set(cited) | claim_ids
    mm_hit = sum(1 for i in ref.must_mention_fact_ids if i in all_cited)
    must_mention_recall = mm_hit / len(ref.must_mention_fact_ids) if ref.must_mention_fact_ids else 1.0
    if must_mention_recall < 1.0:
        categories.append("must_mention_incomplete")

    # 15: fração de claims com evidência válida (não vazia e existente)
    claims_ok = 0
    for c in output.claims:
        valid_ev = [i for i in c.evidence_ids if i in known]
        if valid_ev:
            claims_ok += 1
        else:
            categories.append("claim_evidence_invalid")
    claim_evidence_coverage = claims_ok / len(output.claims) if output.claims else 0.0

    # 16: claim fact não pode ficar sem evidência válida
    for c in output.claims:
        if c.claim_type == "fact" and not [i for i in c.evidence_ids if i in known]:
            categories.append("fact_claim_without_evidence")

    # dedup de categorias preservando ordem
    seen_cat: set[str] = set()
    ordered_cats: list[str] = []
    for cat in categories:
        if cat not in seen_cat:
            seen_cat.add(cat)
            ordered_cats.append(cat)

    # erro de unidade em fato crítico também é hard fail
    for km in output.key_moves:
        fact = facts_by_id.get(km.fact_id)
        if fact is not None and km.unit != fact.unit.value and fact.fact_id in ref.critical_fact_ids:
            hard_fail = True

    return DeterministicGrade(
        case_id=case.case_id,
        task_id=task_id,
        schema_valid=True,
        length_valid=length_valid,
        word_count=wc,
        headline_ok=headline_ok,
        evidence_id_validity=evidence_id_validity,
        key_moves_count_ok=key_moves_count_ok,
        drivers_count_ok=drivers_count_ok,
        critical_fact_recall=critical_fact_recall,
        must_mention_recall=must_mention_recall,
        numeric_accuracy=n_num_ok / n_checked if n_checked else 0.0,
        direction_accuracy=n_dir_ok / n_checked if n_checked else 0.0,
        unit_accuracy=n_unit_ok / n_checked if n_checked else 0.0,
        measure_kind_accuracy=n_mk_ok / n_checked if n_checked else 0.0,
        claim_evidence_coverage=claim_evidence_coverage,
        return_as_contribution_violation="return_as_contribution" in ordered_cats,
        hard_fail=hard_fail,
        failure_categories=ordered_cats,
        details=details,
    )
