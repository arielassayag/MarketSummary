"""Carregamento e validação do dataset congelado + proteção do holdout."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import Case, canonical_json, sha256_obj


class HoldoutAccessError(PermissionError):
    """Comando de desenvolvimento tentou ler o holdout sem flag explícita."""


class CaseValidationError(ValueError):
    def __init__(self, path: Path, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        super().__init__(f"caso inválido {path.name}: {'; '.join(errors)}")


def cases_dir(root: Path, split: str) -> Path:
    return root / "data" / "cases" / split


def list_case_paths(root: Path, split: str, *, allow_holdout: bool = False) -> list[Path]:
    if split == "holdout" and not allow_holdout:
        raise HoldoutAccessError(
            "acesso ao holdout requer flag explícita (--confirm-holdout)"
        )
    directory = cases_dir(root, split)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def load_case(path: Path) -> Case:
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        case = Case.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise CaseValidationError(path, [str(exc)]) from exc
    errors = validate_reference_ids(case)
    if errors:
        raise CaseValidationError(path, errors)
    # case_id do arquivo deve bater com o conteúdo
    expected = path.stem
    if case.case_id != expected:
        raise CaseValidationError(path, [f"case_id '{case.case_id}' != nome do arquivo '{expected}'"])
    return case


def load_cases(root: Path, split: str, *, allow_holdout: bool = False) -> list[Case]:
    return [load_case(p) for p in list_case_paths(root, split, allow_holdout=allow_holdout)]


def validate_reference_ids(case: Case) -> list[str]:
    """IDs de referência precisam existir; sem IDs duplicados nas listas."""
    errors: list[str] = []
    known = case.fact_ids()
    ref = case.reference
    for field_name in ("critical_fact_ids", "must_mention_fact_ids", "useful_fact_ids"):
        ids: list[str] = getattr(ref, field_name)
        for i in ids:
            if i not in known:
                errors.append(f"{field_name}: ID inexistente '{i}'")
        if len(ids) != len(set(ids)):
            errors.append(f"{field_name}: IDs duplicados")
    for i in ref.fact_importance:
        if i not in known:
            errors.append(f"fact_importance: ID inexistente '{i}'")
    for group in ref.accepted_driver_groups:
        for i in group.evidence_ids:
            if i not in known:
                errors.append(f"accepted_driver_groups[{group.label}]: ID inexistente '{i}'")
    return errors


def case_input_hash(case: Case) -> str:
    """Hash do pacote visto pelo modelo (fatos ordenados deterministicamente)."""
    facts = [
        {
            "fact_id": f.fact_id,
            "category": f.category.value,
            "subject": f.subject,
            "statement": f.statement,
            "measure_kind": f.measure_kind.value,
            "value": f.value,
            "unit": f.unit.value,
            "direction": f.direction.value,
        }
        for f in sorted(case.facts, key=lambda f: (f.category.value, f.fact_id))
    ]
    return sha256_obj({"date": case.date, "facts": facts})


def case_reference_hash(case: Case) -> str:
    return sha256_obj(json.loads(canonical_json(case.reference.model_dump(mode="json"))))


@dataclass
class CaseReport:
    case: str
    ok: bool
    split: str = ""
    regime: str = ""
    showcase: bool = False
    review_status: str = "draft"
    n_facts: int = 0
    errors: list[str] = field(default_factory=list)


def validate_dataset(root: Path) -> tuple[list[CaseReport], list[str]]:
    """Validação profunda (comando validate-data). Lê os dois splits (integridade)."""
    reports: list[CaseReport] = []
    total_errors: list[str] = []
    for split in ("dev", "holdout"):
        paths = list_case_paths(root, split, allow_holdout=True)
        for path in paths:
            case_errors: list[str] = []
            try:
                case = load_case(path)
            except CaseValidationError as exc:
                case_errors = exc.errors
                total_errors += [f"{path.name}: {e}" for e in case_errors]
                reports.append(CaseReport(case=path.name, ok=False, split=split, errors=case_errors))
                continue
            if case.split.value != split:
                case_errors.append(f"split do conteúdo ({case.split.value}) != diretório ({split})")
            quantitative = [
                f
                for f in case.facts
                if f.measure_kind.value in ("return_pct", "change_pct", "change_bps", "contribution_bps", "level", "absolute_value")
                and f.value is None
            ]
            if quantitative:
                case_errors.append("fatos quantitativos sem valor")
            contrib = [f for f in case.facts if f.measure_kind == "return_pct" and "contribui" in f.statement.lower()]
            if contrib:
                case_errors.append(f"retorno possivelmente rotulado como contribuição: {[f.fact_id for f in contrib]}")
            total_errors += [f"{path.name}: {e}" for e in case_errors]
            reports.append(
                CaseReport(
                    case=path.name,
                    ok=not case_errors,
                    split=split,
                    regime=case.regime.value,
                    showcase=case.showcase,
                    review_status=case.review.status.value,
                    n_facts=len(case.facts),
                    errors=case_errors,
                )
            )
    return reports, total_errors
